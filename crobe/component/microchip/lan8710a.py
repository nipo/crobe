from .. import ethernet_phy
from ...protocol import smi, jtag
from ...part_id import PartId
from ... import bitfield
from ...util.pretty import metric
from ...util.bit import *
from ...util.timeout import *
from .. import ethernet_phy
import enum

class Register(enum.IntEnum):
    Control = 0
    Status = 1
    PhyId0 = 2
    PhyId1 = 3
    AutoNegAdv = 4
    AutoNegPartnerBase = 5
    AutoNegExpansion = 6
    ModeControlStatus = 17
    SpecialModes = 18
    SymbolErrorCounter = 26
    ControlStatusIndication = 27
    InterruptSource = 29
    InterruptMask = 30
    PhySpecialControlStatus = 31

class ModeControlStatus(bitfield.Bitfield):
    edpwrdown = bitfield.BooleanField(13)
    farloopback = bitfield.BooleanField(9)
    altint = bitfield.BooleanField(6)
    energyon = bitfield.BooleanField(1)

class AutoNegExpansion(bitfield.Bitfield):
    res = bitfield.Field(7, 9)
    rx_np_able = bitfield.BooleanField(6)
    rx_np_store = bitfield.BooleanField(5)
    pdf = bitfield.BooleanField(4)
    lp_np_able = bitfield.BooleanField(3)
    np_able = bitfield.BooleanField(2)
    page_rx = bitfield.BooleanField(1)
    lp_np_able = bitfield.BooleanField(0)

class SpecialModes(bitfield.Bitfield):
    rmii = bitfield.BooleanField(14)
    mode = bitfield.MappingField(5, 3, ["10bthd", "10btfd", "100bthd", "100btfd", "autoneg-100bt", "repeater", "power_down", "autoneg-all"])
    phyad = bitfield.Field(0, 5)

class ControlStatusIndication(bitfield.Bitfield):
    amdixctrl = bitfield.BooleanField(15)
    ch_select = bitfield.BooleanField(13)
    sqeoff = bitfield.BooleanField(11)
    xpol = bitfield.BooleanField(4)

class Interrupt(bitfield.Bitfield):
    energyon = bitfield.BooleanField(7)
    autoneg = bitfield.BooleanField(6)
    remote_fault = bitfield.BooleanField(5)
    link_down = bitfield.BooleanField(4)
    autoneg_ack = bitfield.BooleanField(3)
    par_detec_fault = bitfield.BooleanField(2)
    autoneg_page = bitfield.BooleanField(1)

class PhySpecialControlStatus(bitfield.Bitfield):
    autodone = bitfield.BooleanField(12)
    enable_4b5b = bitfield.BooleanField(6)
    speed = bitfield.MappingField(2, 2, {0: "off", 1: "10bt", 2: "100bt"})
    fd = bitfield.BooleanField(4)
    
@smi.Interface.db.register(0x000740f1)
class Lan8710(ethernet_phy.Clause22EthernetPhy):
    REGISTERS = Register
    REGISTER_MAP = dict(ethernet_phy.Clause22EthernetPhy.REGISTER_MAP.items())
    REGISTER_MAP.update({
        Register.SpecialModes: SpecialModes,
        Register.ModeControlStatus: ModeControlStatus,
        Register.ControlStatusIndication: ControlStatusIndication,
        Register.InterruptSource: Interrupt,
        Register.InterruptMask: Interrupt,
        Register.PhySpecialControlStatus: PhySpecialControlStatus,
    })

    def __init__(self, port, name = "lan8710", phyad = None):
        super().__init__(port, name, phyad)
