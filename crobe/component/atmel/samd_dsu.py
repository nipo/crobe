from ...model import Bus32Component
from ..arm.coresight.rom_table import RomTable
from ...part_id import PartId
import time
import enum

@RomTable.db.register(PartId(0, 0x1f, 0xcd0, 0))
class DsuRom(RomTable):
    def start(self):
        super().start()
        self.child_add(Dsu(self.bus, self.base - 0x1000))

class Dsu(Bus32Component):
    def __init__(self, bus, base):
        super().__init__(bus, base, "DSU")
        
    def __str__(self):
        return "Atmel SAM DSU"
        
    def start(self):
        super().start()
        self.logger.info("DID: %08x", self.reg_read(self.Reg.DID))

    def reg8_read(self, offset):
        op = self.cmd_reg8_read(offset)
        self.bus.execute([op])
        return op.data

    def reg8_write(self, offset, data):
        op = self.cmd_reg8_write(offset, data)
        self.bus.execute([op])

    def cmd_reg8_read(self, offset):
        return self.bus.cmd_u8_read(self.base + offset)

    def cmd_reg8_write(self, offset, data, interval = 0):
        return self.bus.cmd_u8_write(self.base + offset, data, interval)

    def chip_erase(self):
        self.reg8_write(self.Reg.CTRL, 0x10)
        while not self.reg8_read(self.Reg.STATUSA) & 0x01:
            time.sleep(.01)
        self.reg8_write(self.Reg.CTRL, 0x01)

    class Reg(enum.IntEnum):
        CTRL    = 0x0
        STATUSA = 0x1
        STATUSB = 0x2
        ADDR    = 0x4
        LENGTH  = 0x8
        DATA    = 0xc
        DCC0    = 0x10
        DCC1    = 0x14
        DID     = 0x18
        DCFG0   = 0xf0
        DCFG1   = 0xf4
