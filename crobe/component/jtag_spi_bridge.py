from ..protocol import spi
import binascii

__all__ = ["JtagSpiBridge"]

class JtagSpiBridge(spi.Interface):
    def __init__(self, tap, data_in, data_out, base_freq):
        spi.Interface.__init__(self, tap)
        self.data_in_ir = data_in
        self.data_out_ir = data_out
        self.base_freq = base_freq
        self.__div = 0

    @property
    def freq(self):
        return self.base_freq / (self.__div + 1)

    @freq.setter
    def freq(self, freq):
        if not freq:
            self.__div = 0
        self.__div = max(0, min(0x1f, int(self.base_freq / freq + .5)))

    CMD_SELECT = 0x00
    CMD_SHIFT_OUT = 0x80
    CMD_SHIFT_IN = 0x40
    CMD_SHIFT_IO = 0xc0
    CMD_UNSELECT = 0x1f
    CMD_DIV = 0x20

    def cmd_io(self, cmd, rsp_size):
        padding_time = max(0, rsp_size - len(cmd)) * 8 / self.freq
        padding_bits = int(padding_time * self.port.port.port.freq)

        self.logger.debug("CMD %s, rsp %d bytes, padding %d bits", binascii.b2a_hex(cmd), rsp_size, padding_bits)

        return [
            self.port.cmd_dr_shift(self.data_in_ir, b"\x5c\xad" + cmd, read_tdo = False),
            self.port.cmd_run(padding_bits + 16),
            self.port.cmd_dr_shift(self.data_out_ir, None, 8 * rsp_size, read_tdo = True, return_type = bytes),
        ]

    def _execute(self, operation_list):
        pending = []

        for op in operation_list:
            pending += self.cmd_io(bytes([self.CMD_DIV | self.__div]), 1)

            if isinstance(op, spi.Shift):
                op.__rsp = []

                if isinstance(op.mosi, int):
                    for off in range(0, op.mosi, 64):
                        cs = min(64, op.mosi - off)
                        pending += self.cmd_io(bytes([self.CMD_SHIFT_IN | (cs - 1)]), 1 + cs)
                        op.__rsp.append(pending[-1])
                else:
                    cc = self.CMD_SHIFT_IO if op.read_miso else self.CMD_SHIFT_OUT
                    for off in range(0, len(op.mosi), 64):
                        chunk = op.mosi[off : off + 64]
                        cs = len(chunk)
                        pending += self.cmd_io(bytes([cc | (cs - 1)]) + chunk,
                                               (1 + cs) if op.read_miso else 1)
                        op.__rsp.append(pending[-1])

            elif isinstance(op, spi.Cs):
                pending += self.cmd_io(bytes([self.CMD_SELECT if op.value else self.CMD_UNSELECT]), 1)

            else:
                raise base.ProtocolError("Unknown SPI operation %s" % type(op))

        self.port.execute(pending)

        for op in operation_list:
            if isinstance(op, spi.Shift) and op.read_miso:
                op.miso = b''.join([o.tdo[1:] for o in op.__rsp])
