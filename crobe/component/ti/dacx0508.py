from ...model import PortComponent
from ...protocol import spi
import enum

class Register(enum.IntEnum):
    Nop = 0
    DeviceId = 1
    Sync = 2
    Config = 3
    Gain = 4
    Trigger = 5
    Brdcast = 6
    Status = 7
    Dac0 = 8
    Dac1 = 9
    Dac2 = 0xa
    Dac3 = 0xb
    Dac4 = 0xc
    Dac5 = 0xd
    Dac6 = 0xe
    Dac7 = 0xf

@spi.Target.db.register("dacx0508")
class Dacx0508(PortComponent):
    def __init__(self, port):
        super().__init__(port, "dacx0508")

    def reg_read(self, reg):
        cmd = self.port.cmd_shift(bytes([0x80 | int(reg), 0, 0]), read_miso = False)
        cmd2 = self.port.cmd_shift(bytes([0]), read_miso = False)
        data = self.port.cmd_shift(b"\x00" * 2, read_miso = True)

        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False),
                           self.port.cmd_cs(True), cmd2, data, self.port.cmd_cs(False)])

        return int.from_bytes(data.miso, "big")

    def reg_write(self, reg, value):
        blob = int(value).to_bytes(2, "big")

        cmd = self.port.cmd_shift(bytes([int(reg)]) + blob, read_miso = False)

        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])

    def channel_write(self, no, value):
        self.reg_write(int(Registers.Dac0) + no, value)
        
    def start(self):
        devid = self.reg_read(Register.DeviceId)

        resolution = (devid >> 12) & 0x7
        resolution_bits = {0: 16, 1: 14, 2: 12}

        channels = (devid >> 8) & 0xf

        variant = "Z" if devid & 0x80 else "M"

        self.logger.note("DACx0508, %s-bit resolution, %d channels, Variant %s",
                         resolution_bits.get(resolution, "?"), channels, variant);
