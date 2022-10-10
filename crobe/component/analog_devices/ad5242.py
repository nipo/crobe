from ...model import PortComponent
from ...protocol import i2c
import enum

@i2c.Interface.db.register("ad5242")
class Ad5242(i2c.Slave):
    def __init__(self, port, saddr = 0x2c):
        super().__init__(port, "ad5242", saddr)
        
    def rdac_set(self, channel, value, shutdown = False):
        op = (0x80 if channel else 0)
        op |= (0x20 if shutdown else 0)
        value = int(value)
        self.write(bytes([op, value]))
