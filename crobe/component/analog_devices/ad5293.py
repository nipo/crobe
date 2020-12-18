from ...model import PortComponent
from ...protocol import spi
import enum

class Opcode(enum.IntEnum):
    Nop = 0
    Write = 1
    Read = 2
    Reset = 4
    ControlWrite = 6
    ControlRead = 7
    PowerDown = 8

@spi.Target.db.register("ad5293")
class Ad5293(PortComponent):
    def __init__(self, port):
        super().__init__(port, "ad5293")

    def opcode_send(self, opcode, arg):
        word = int(arg) | (int(opcode) << 10)
        cmd = self.port.cmd_shift(word.to_bytes(2, "big"), read_miso = False)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])

    def rdac_set(self, value):
        self.opcode_send(Opcode.Write, value)

    def control_set(self, calibration = False, rdac_protect = False):
        value = 0
        if calibration:
            value |= 0x4
        if not rdac_protect:
            value |= 0x2
        self.opcode_send(Opcode.ControlWrite, value)

    def powerdown_set(self, shutdown = False):
        value = int(bool(shutdown))
        self.opcode_send(Opcode.PowerDown, value)

    def rdac_reset(self):
        self.opcode_send(Opcode.Reset, 0)
