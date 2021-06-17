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

    def start(self):
        super().start()
        self.read(0)
        
    def write(self, opcode, arg = 0):
        """
        Write one opcode with argument.
        Issues SDO release command after.
        """
        word = int(arg) | (int(opcode) << 10)
        cmd = self.port.cmd_shift(word.to_bytes(2, "big"), read_miso = True)
        self.port.execute([
            self.port.cmd_cs(True), cmd, self.port.cmd_cs(False),
            self.port.cmd_cs(True), self.port.cmd_shift(b'\x80\x01', read_miso = False), self.port.cmd_cs(False),
            self.port.cmd_cs(True), self.port.cmd_shift(b'\x00\x00', read_miso = False), self.port.cmd_cs(False),
        ])

    def read(self, opcode):
        """
        Read one opcode.
        Issues SDO release command after.
        """
        word = int(opcode) << 10
        w = self.port.cmd_shift(word.to_bytes(2, "big"), read_miso = True)
        r = self.port.cmd_shift(b'\x00\x00', read_miso = True)
        self.port.execute([
            self.port.cmd_cs(True), w, self.port.cmd_cs(False),
            self.port.cmd_cs(True), r, self.port.cmd_cs(False),
            self.port.cmd_cs(True), self.port.cmd_shift(b'\x80\x01', read_miso = False), self.port.cmd_cs(False),
            self.port.cmd_cs(True), self.port.cmd_shift(b'\x00\x00', read_miso = False), self.port.cmd_cs(False),
        ])
        return int.from_bytes(r.miso, "big") & 0x03ff

    def rdac_set(self, value):
        """
        Sets RDAC register.

        This does not unlock the RDAC. You should ensure it is writable.
        """
        self.write(Opcode.Write, value & 0x3ff)

    def rdac_get(self):
        """
        Reads RDAC register.
        """
        return self.read(Opcode.Read)

    def control_set(self, calibration = False, rdac_protect = False):
        """
        Sets control bits.
        """
        value = 0
        if calibration:
            value |= 0x4
        if not rdac_protect:
            value |= 0x2
        self.write(Opcode.ControlWrite, value)

    def control_get(self):
        """
        Get control bits.
        """
        v = self.read(Opcode.ControlRead)
        return dict(
            calibration = bool(v & 0x4),
            rdac_protect = not (v & 0x2),
            )

    def powerdown_set(self, shutdown = False):
        """
        Sets powerdown state.
        """
        self.write(Opcode.PowerDown, int(bool(shutdown)))

    def rdac_reset(self):
        """
        Beware: this also reset the RDAC protect bit in control register
        """
        self.write(Opcode.Reset)

    def nop(self):
        """
        Useless operation.
        """
        self.write(Opcode.Nop)
