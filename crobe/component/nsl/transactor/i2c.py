from ....model import PortComponent
from ....protocol import base, i2c
from ....util.pretty import metric
import math

class I2cTransactor(PortComponent):
    CMD_READ_ACK     = 0xc0
    CMD_READ_NACK    = 0x80
    CMD_WRITE        = 0x40
    CMD_START        = 0x20
    CMD_STOP         = 0x21
    CMD_DIV          = 0x00

    pre_div = 2**5
    
    def __init__(self, route, base_freq):
        self.base_freq = base_freq

        super().__init__(route, "i2c")

        self.logger.note("NSL i2c transactor with internal clock of %s", metric(self.base_freq, "Hz"))
        self.__div = 4

    def freq_update(self, freq):
        if self.base_freq is None:
            return 0
        if not freq:
            freq = 1e6
        d = math.ceil(self.base_freq / float(freq) / self.pre_div / 2)
        self.__div = min(0x1f, max(2, d))

        return self.base_freq / self.__div / self.pre_div / 2

    def execute(self, operation_list):
        ops = list(operation_list)
        cmd = [self.CMD_DIV | self.__div]
        rsp_size = 1
        rsp_total_size = 0
        rsp = b''
        starts = []

        prev = None
        for i, cur in enumerate(ops):
            #self.logger.info("op %d %s", i, cur)

            next = ops[i+1] if i < len(ops) - 1 else None

            if not prev or (isinstance(prev, i2c.Read) != isinstance(cur, i2c.Read)):
                cmd.append(self.CMD_START)
                rsp_size += 1
                cmd += [self.CMD_WRITE | 0, (cur.addr << 1) | int(isinstance(cur, i2c.Read))]
                starts.append((cur, rsp_total_size + rsp_size))
                rsp_size += 1

            last = not next or (isinstance(cur, i2c.Read) != isinstance(next, i2c.Read))

            if isinstance(cur, i2c.Read):
                cur.__rsp = []
                for offset in range(0, cur.size, 0x40):
                    last_offset = cur.size - 0x40 <= offset
                    size = min(cur.size - offset, 0x40)
                    cur.__rsp.append((rsp_total_size + rsp_size,
                                      rsp_total_size + rsp_size + size))
                    rsp_size += size

                    if last and last_offset:
                        cmd.append(self.CMD_READ_NACK | (size - 1))
                    else:
                        cmd.append(self.CMD_READ_ACK | (size - 1))
        
            elif isinstance(cur, i2c.Write):
                cur.__rsp = []
                for offset in range(0, len(cur.data), 0x40):
                    size = min(len(cur.data) - offset, 0x40)
                    cur.__rsp.append((rsp_total_size + rsp_size,
                                      rsp_total_size + rsp_size + size))
                    rsp_size += size

                    cmd.append(self.CMD_WRITE | (size - 1))
                    cmd += cur.data[offset : offset + size]

            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))

            prev = cur

        cmd.append(self.CMD_STOP)
        rsp_size += 1

        #self.logger.protocol("Running %s", bytes(cmd).hex())
        rsp += self.port.execute(bytes(cmd), rsp_size)

        for op, s in starts:
            if not rsp[s]:
                raise i2c.AddressNack(op.addr)

        for op in ops:
            data = b''.join(rsp[start:end] for (start, end) in op.__rsp)
            if isinstance(op, i2c.Read):
                op.data = data
            elif not all(data[:-1]):
                raise i2c.DataNack()
