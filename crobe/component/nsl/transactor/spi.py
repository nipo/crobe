from ....util.pretty import metric
from ....model import PortComponent
from ....protocol import base, spi
from ....bitstring import BitString
import math

class SpiTransactor(PortComponent):
    CMD_SHIFT_OUT      = 0x80 # | 6 bits byte count -1
    CMD_SHIFT_IN       = 0x40 # | 6 bits byte count -1
    CMD_SHIFT_INOUT    = 0xc0 # | 6 bits byte count -1
    CMD_SELECT         = 0x00 # | cpol(bit 4) | cpha(bit 3) | 3 bits slave id
    CMD_UNSELECT       = 0x07 # i.e. select(-1)
    CMD_DIVISOR        = 0x20 # | 5 bits divisor
    
    def __init__(self, route, base_freq):
        self.base_freq = base_freq

        super().__init__(route, "spi")

        self.logger.info("NSL SPI Transactor with internal clock of %s", metric(self.base_freq, "Hz"))

        self.__divisor = int(self.base_freq / 1e6) - 1
        self.__rate_dirty = True
        
    def freq_update(self, freq):
        if self.base_freq is None:
            return 0
        if not freq:
            freq = 15e6
        divisor = int(math.ceil(self.base_freq / 2. / float(freq))) - 1
        next_divisor = max(0, min(divisor, 0x1f))
        if self.__divisor != next_divisor:
            self.__divisor = next_divisor
            self.__rate_dirty = True
        return self.base_freq / ((self.__divisor + 1) * 2)
    
    def execute(self, operation_list):
        pending = []
        rsp_size = 0
        mode = 0

        self.logger.debug("Running %s", operation_list)
        
        for op in operation_list:
            if self.__rate_dirty:
                pending.append(bytes([self.CMD_DIVISOR | self.__divisor]))
                rsp_size += 1
                self.__rate_dirty = False

            if isinstance(op, spi.Shift) and isinstance(op.mosi, int) and op.read_miso:
                op.miso = b''
                op.__gather = []
                for off in range(0, op.mosi, 0x40):
                    left = min(0x40, op.mosi - off)
                    pending.append(bytes([self.CMD_SHIFT_IN | (left - 1)]))
                    rsp_size += 1
                    op.__gather.append((rsp_size, left))
                    rsp_size += left
            elif isinstance(op, spi.Shift) and not isinstance(op.mosi, int) and op.read_miso:
                op.miso = b''
                op.__gather = []
                for off in range(0, len(op.mosi), 0x40):
                    left = min(0x40, len(op.mosi) - off)
                    pending.append(bytes([self.CMD_SHIFT_INOUT | (left - 1)]) + op.mosi[off : off + left])
                    rsp_size += 1
                    op.__gather.append((rsp_size, left))
                    rsp_size += left
            elif isinstance(op, spi.Shift) and not isinstance(op.mosi, int) and not op.read_miso:
                op.miso = None
                op.__gather = []
                for off in range(0, len(op.mosi), 0x40):
                    left = min(0x40, len(op.mosi) - off)
                    pending.append(bytes([self.CMD_SHIFT_OUT | (left - 1)]) + op.mosi[off : off + left])
                    rsp_size += 1

            elif isinstance(op, spi.Shift):
                raise NotImplementedError(op)

            elif isinstance(op, spi.Cs):
                if op.value is not None:
                    mode = op.mode
                    opcode = self.CMD_SELECT | (op.mode << 3) | op.value
                else:
                    opcode = self.CMD_UNSELECT | (mode << 3)
                pending.append(bytes([opcode]))
                rsp_size += 1

            else:
                raise base.ProtocolError("Unknown SPI operation %s" % type(op))

        cmd = b''.join(pending)
        rsp = self.port.execute(cmd, rsp_size)

        for op in operation_list:
            if isinstance(op, spi.Shift) and op.__gather:
                op.miso = b''.join(rsp[off : off + size] for (off, size) in op.__gather)

