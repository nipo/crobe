from ...protocol import i2c
from ...model import PortComponent
import struct
import time

from . import atsec

@i2c.Interface.db.register("atsha204a")
@i2c.Interface.db.register("atsha")
class AtSha204A(atsec.AtSec):
    def __init__(self, bus, saddr = None):
        super().__init__(bus, name = "atsha204a", saddr = saddr)

    def read(self, zone, offset, size):
        if zone == 1:
            read_size = 4
        else:
            read_size = 32
            zone |= 0x80
        start = offset & ~(read_size - 1)
        end = (offset + size + read_size - 1) & ~(read_size - 1)
        s = end - start
        blob = b''
        for o in range(0, s, read_size):
            blob += self.command_execute(0x02, zone, (start + o) // 4)
        print(zone, offset, size, read_size, blob.hex())
        return blob[offset - start : offset - start + size]

    def otp_read(self):
        return self.read(1, 0, 64)

    def start(self):
        super().start()
        assert self.product.startswith("ATSHA")
