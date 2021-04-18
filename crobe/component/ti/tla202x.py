from ...model import PortComponent
from ...protocol import i2c
import enum

class Reg(enum.IntEnum):
    Data = 0
    Config = 1

class Tla202x(i2c.Slave):
    def __init__(self, bus, saddr):
        super().__init__(bus, "tla202x", saddr)

    def reg_read(self, reg, signed = False):
        reg = int(reg)
        addr = bytes([reg])

        rdata = self.write_read(addr, 2)
        value = int.from_bytes(rdata, "big", signed = signed)

        self.logger.debug("Reg read %d: 0x%04x", reg, value)

        return value

    def reg_write(self, reg, value):
        reg = int(reg)
        addr = bytes([reg])
        data = int(value).to_bytes(2, "big")

        self.logger.debug("Reg write %s: 0x%04x", reg, int(value))

        self.write(addr + data)

    def convert(self, mux, pga = 0x2):
        config = (mux << 12) | (pga << 9) | 0x103
        self.reg_write(Reg.Config, config)
        self.reg_write(Reg.Config, config | 0x8000)
        while True:
            status = self.reg_read(Reg.Config)
            if status & 0x8000:
                break
        value = self.reg_read(Reg.Data, signed = True)
        lsb = [3e-3, 2e-3, 1e-3, 5e-4, 25e-5, 125e-6, 125e-6, 125e-6]
        return (value >> 4) * lsb[pga]
        
@i2c.Interface.db.register("tla202x")
def tla202x_get(bus):
    return Tla202x(bus, None)
