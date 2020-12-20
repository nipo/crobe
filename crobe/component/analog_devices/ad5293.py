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

    def opcode_send(self, opcode, arg, read_miso = False):
        word = int(arg) | (int(opcode) << 10)
        cmd = self.port.cmd_shift(word.to_bytes(2, "big"), read_miso = read_miso)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])
        if read_miso:
            return int.from_bytes(cmd.miso, "big")

    def rdac_set(self, value):
        self.opcode_send(Opcode.Write, value)

    def rdac_get(self):
        self.opcode_send(Opcode.Read, 0)
        return self.opcode_send(Opcode.Nop, 0, read_miso = True)

    def control_set(self, calibration = False, rdac_protect = False):
        value = 0
        if calibration:
            value |= 0x4
        if not rdac_protect:
            value |= 0x2
        self.opcode_send(Opcode.ControlWrite, value)

    def control_get(self):
        self.opcode_send(Opcode.ControlRead, 0)
        return self.opcode_send(Opcode.Nop, 0)

    def powerdown_set(self, shutdown = False):
        value = int(bool(shutdown))
        self.opcode_send(Opcode.PowerDown, value)

    def rdac_reset(self):
        self.opcode_send(Opcode.Reset, 0)
