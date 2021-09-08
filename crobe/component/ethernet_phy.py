from ..protocol import smi
from .. import bitfield
import enum

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

class Status(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    extended = bitfield.BooleanField(0)
    jabber_detect = bitfield.BooleanField(1)
    link = bitfield.BooleanField(2)
    autoneg_able = bitfield.BooleanField(3)
    remote_fault = bitfield.BooleanField(4)
    autoneg_done = bitfield.BooleanField(5)
    mf_pre_suppr = bitfield.BooleanField(6)
    ext_status = bitfield.BooleanField(8)
    tech_100bt2 = bitfield.BooleanField(9)
    tech_100bt2_fd = bitfield.BooleanField(10)
    tech_10bte = bitfield.BooleanField(11)
    tech_10bte_fd = bitfield.BooleanField(12)
    tech_100btx = bitfield.BooleanField(13)
    tech_100btx_fd = bitfield.BooleanField(14)
    tech_100bt4 = bitfield.BooleanField(15)

class BasePage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    selector = bitfield.Field(0, 5)
    ability = bitfield.Field(5, 7)
    t = bitfield.BooleanField(11)
    xnp = bitfield.BooleanField(12)
    rf = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)

class MessagePage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    message = bitfield.Field(0, 11)
    t = bitfield.BooleanField(11)
    # Can comply
    ack2 = bitfield.BooleanField(12)
    # Should be 1
    mp = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)

class UnformattedPage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    u = bitfield.Field(0, 11)
    t = bitfield.BooleanField(11)
    # Can comply
    ack2 = bitfield.BooleanField(12)
    # Should be 0
    mp = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)
    
@smi.Interface.db.register("eth_phy")
@smi.Interface.db.register_default
class Clause22EthernetPhy(smi.C22Slave):
    def __init__(self, bus, name = "phy", phyad = None):
        super().__init__(bus, name = name, phyad = phyad)

    def reg_set(self, no, value):
        if reg <= 0x1f:
            return self.write(no, value)
        else:
            return self.ext_write(0x1f, no, value)

    def reg_get(self, no):
        if reg <= 0x1f:
            return self.read(no)
        else:
            return self.ext_read(0x1f, no)

