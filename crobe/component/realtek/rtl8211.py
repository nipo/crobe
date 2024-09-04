from .. import ethernet_phy
from ...protocol import smi
from ...part_id import PartId
from ... import bitfield
import enum
from .rtl82 import RtlHighPagedPhy, paged_address

class Register:
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
    INER   = paged_address(18, 0xa42) # RW Interrupt Enable Register.
    PHYCR1 = paged_address(24, 0xa43) # RW PHY Specific Control Register 1.
    PHYCR2 = paged_address(25, 0xa43) # RW PHY Specific Control Register 2.
    PHYSR  = paged_address(26, 0xa43) # RO PHY Specific Status Register.
    INSR   = paged_address(29, 0xa43) # RO Interrupt Status Register.
    PAGSR  = paged_address(31, 0xa43) # RW Page Select Register.
    PHYSCR = paged_address(20, 0xa46) # RW PHY Special Cofig Register
    LCR    = paged_address(16, 0xd04) # RW LED Control Register
    EEELCR = paged_address(17, 0xd04) # RW EEE LED Control Register.
    MIICR  = paged_address(21, 0xd08) # RW MII Control Register
    INTBCR = paged_address(22, 0xd40) # RW INTB Pin Control Register.
    
@smi.Interface.db.register("rtl8211")
class Rtl8211(RtlHighPagedPhy):
    def __init__(self, port, name = "rtl8211", phyad = None):
        super().__init__(port, name, phyad)

@smi.Interface.db.register("rtl8211f")
@smi.Interface.db.register(0x001cc916)
class Rtl8211F(Rtl8211):
    def __init__(self, port, name = "rtl8211f", phyad = None):
        super().__init__(port, name, phyad)
        
