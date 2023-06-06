from ...model import PortComponent
from ...protocol import i2c
import enum

@i2c.Interface.db.register("mcp4726")
class Mcp4726(i2c.Slave):
    VREF_VDD = 0
    VREF_EXT = 2
    VREF_EXT_BUF = 3

    def __init__(self, port, saddr = 0x60):
        super().__init__(port, "mcp4726", saddr)

    def dac_set(self, value):
        self.write((value & 0xfff).to_bytes(2, "big"))

    def volatile_set(self, value, vref = 0, pd = 0, g = 0):
        v = 0x400000
        v |= int(bool(g)) << 16
        v |= (pd & 3) << 17
        v |= (vref & 3) << 19
        v |= (value & 0xfff) << 4
        self.write(v.to_bytes(3, "big"))

    def config_set(self, vref = 0, pd = 0, g = 0):
        v = 0x80
        v |= int(bool(g))
        v |= (pd & 3) << 1
        v |= (vref & 3) << 3
        self.write(v.to_bytes(1, "big"))
