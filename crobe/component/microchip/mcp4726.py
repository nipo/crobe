from ...model import PortComponent
from ...protocol import i2c
import enum

@i2c.Interface.db.register("mcp4726")
class Mcp4726(i2c.Slave):
    def __init__(self, port, saddr = 0x60):
        super().__init__(port, "mcp4726", saddr)

    def dac_set(self, value):
        self.write((value & 0xfff).to_bytes(2, "big"))
