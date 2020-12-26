from ..protocol import smi
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

@smi.Interface.db.register("eth_phy")
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

