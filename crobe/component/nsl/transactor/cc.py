from ....model import PortComponent
from ....protocol import base, chipcon

class CcTransactor(PortComponent):
    CMD_CMD          = staticmethod(lambda out_count, in_count, wait: (in_count | ((out_count - 1) << 2)) | (int(bool(wait)) << 4))
    CMD_ACQUIRE      = 0x20
    CMD_RESET        = 0x21
    CMD_WAIT         = staticmethod(lambda d: (0x40 | d))
    CMD_DIV          = staticmethod(lambda d: (0xc0 | (0x3f & (d-1))))

    def __init__(self, route, base_freq):
        self.base_freq = base_freq

        super().__init__(route, "cc")

        self.logger.info("NSL CC transactor with internal clock of %s", metric(self.base_freq, "Hz"))
        self.__reset = False
        self.__div = 16

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        if self.__reset and not value:
            self.logger.info("toggling reset pin")
            cmds = bytes([self.CMD_DIV(0x40), self.CMD_RESET])
            self.port.execute(cmds, 2)

        self.__reset = bool(value)
        
    def freq_update(self, freq):
        if self.base_freq is None:
            return 0
        if not freq:
            freq = self.base_freq
        self.__div = max(1, min(0x40, int(self.base_freq / float(freq) / 2 / 4)))
        self.logger.info("Divisor now %d", self.__div)

        return self.base_freq / self.__div / 2 / 4

    def execute(self, operation_list):
        ops = list(operation_list)

        commands = []
        response_lengths = []
        for op in ops:
            if isinstance(op, chipcon.DebugInit):
                commands.append(bytes([self.CMD_DIV(0x40), self.CMD_ACQUIRE,
                                       self.CMD_WAIT(0x3f), self.CMD_DIV(self.__div)]))
                response_lengths.append(4)

            elif isinstance(op, chipcon.Command):
                commands.append(bytes([self.CMD_CMD(len(op.command), op.rlen, op.should_wait)])
                                + op.command)
                op.__offset = sum(response_lengths) + 1
                response_lengths.append(op.rlen + 1)

            elif isinstance(op, chipcon.BurstWrite):
                assert 1 <= len(op.data) <= 2048
                c = (len(op.data) & 0x2ff) | 0x8000
                blob = c.to_bytes(2, "big") + bytes(op.data)
                for off in range(0, len(blob), 4):
                    last = off + 4 >= len(blob)
                    chunk = blob[off : off + 4]
                    commands.append(bytes([self.CMD_CMD(len(chunk), int(last), last)]
                                          + list(chunk)))
                    response_lengths.append(1 + int(last))

            elif isinstance(op, chipcon.Wait):
                cycles = op.cycles * 2 // 64
                commands.append(bytes([self.CMD_DIV(64)]))
                response_lengths.append(1)
                while cycles:
                    taken = min(0x40, cycles)
                    commands.append(bytes([self.CMD_WAIT(taken - 1)]))
                    response_lengths.append(1)
                    cycles -= taken
                commands.append(bytes([self.CMD_DIV(self.__div)]))
                response_lengths.append(1)

            else:
                raise base.ProtocolError("Unknown CC operation %s" % type(op))

        rsp = b''
        cmd = b''
        rsp_len = 0
        for i, (c, r) in enumerate(zip(commands, response_lengths)):
            cmd += c
            rsp_len += r

            if len(cmd) > 2000 or rsp_len > 2000 or i == len(commands) - 1:
                rsp += self.port.execute(cmd, rsp_len)
                cmd = b''
                rsp_len = 0

        for op in ops:
            if isinstance(op, chipcon.Command):
                op.data = rsp[op.__offset:op.__offset + op.rlen]
