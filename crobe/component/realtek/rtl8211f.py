from .. import ethernet_phy
from ...protocol import smi, jtag
from ...part_id import PartId
from ...util.pretty import metric
from ...util.bit import *
from ...util.timeout import *
import enum

def banked(bank, reg):
    return (bank << 3) | (reg & 0x7)

class Register(enum.IntEnum):
    Control = 0
    Status = 1
    PhyId0 = 2
    PhyId1 = 3
    AutoNegAdv = 4
    AutoNegPartnerBase = 5
    AutoNegExpansion = 6
    AutoNegNextPageTransmit = 7
    AutoNegNextPageReceive = 8
    MasterSlaveControl = 9
    MasterSlaveStatus = 10
    PseControl = 11
    PseStatus = 12
    MmdAccessControl = 13
    MmdAccessAddressData = 14
    ExtendedStatus = 15
    INER   = banked(0xa42, 18) # RW Interrupt Enable Register.
    PHYCR1 = banked(0xa43, 24) # RW PHY Specific Control Register 1.
    PHYCR2 = banked(0xa43, 25) # RW PHY Specific Control Register 2.
    PHYSR  = banked(0xa43, 26) # RO PHY Specific Status Register.
    INSR   = banked(0xa43, 29) # RO Interrupt Status Register.
    PAGSR  = banked(0xa43, 31) # RW Page Select Register.
    PHYSCR = banked(0xa46, 20) # RW PHY Special Cofig Register
    LCR    = banked(0xd04, 16) # RW LED Control Register
    EEELCR = banked(0xd04, 17) # RW EEE LED Control Register.
    MIICR  = banked(0xd08, 21) # RW MII Control Register
    INTBCR = banked(0xd40, 22) # RW INTB Pin Control Register.

class Genesis():
    def __init__(self, bus, name = "genesis", phyad = None):
        super().__init__(bus, name = name, phyad = phyad)

@smi.Interface.db.register("rtl8211f")
@smi.Interface.db.register(0x001cc916)
class Dp83867(ethernet_phy.Clause22EthernetPhy):
    def __init__(self, port, name = "rtl8211f", phyad = None):
        super().__init__(port, name, phyad)

    def paged_read(self, page, reg):
        page = self.cmd_write(0x1f, page)
        rdata = self.cmd_read(reg)
        self.execute([page, rdata])
        return rdata.data

    def paged_write(self, page, reg, data):
        page = self.cmd_write(0x1f, page)
        wdata = self.cmd_write(reg, data)
        self.execute([page, wdata])

    def reg_get(self, reg):
        if reg < 0x10 or 0x18 <= reg <= 0x1f:
            return self.read(reg)
        page = self.cmd_write(0x1f, 0xa40 + (reg >> 3))
        rdata = self.cmd_read(0x10 | (reg & 0x7))
        self.execute([page, rdata])
        return rdata.data

    def reg_set(self, reg, data):
        if reg < 0x10 or 0x18 <= reg <= 0x1f:
            return self.write(reg, data)
        page = self.cmd_write(0x1f, 0xa40 + (reg >> 3))
        wdata = self.cmd_write(0x10 | (reg & 0x7), data)
        self.execute([page, wdata])
