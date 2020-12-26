from .. import ethernet_phy
from ...protocol import smi
from ...bitfield import *
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
    GigStatus = 0x0f
    PhyControl = 0x10
    PhyStatus = 0x11
    MiiIrqMask = 0x12
    MiiIrq = 0x13
    Config2 = 0x14
    ReceiveError = 0x15
    BistControl = 0x16
    Status2 = 0x17
    LedControl1 = 0x18
    LedControl2 = 0x19
    LedControl3 = 0x1a
    Config3 = 0x1e
    Reset = 0x1f
    TestModeChannel = 0x25
    RobustAutoMdixConfig = 0x2c
    FastLinkDropConfig = 0x2d
    FastLinkDropThreshold = 0x2e
    Config4 = 0x31
    RgmiiControl = 0x32
    RgmiiControl2 = 0x33
    SgmiiAutoneg = 0x37
    HundredBaseTXConfig = 0x43
    ViterbiModuleConfig = 0x53
    SkewFifoStatus = 0x55
    StrapStatus1 = 0x6e
    StrapStatus2 = 0x6f
    BistControl1 = 0x71
    BistControl2 = 0x72
    BistControl3 = 0x7b
    BistControl4 = 0x7c
    RgmiiDelay = 0x86
    PllControl = 0xc6
    SgmiiControl1 = 0xd3
    SyncFifoControl = 0xe9
    LoopbackConfig = 0xfe
    DspFeedforwardEqualizerConfig = 0x12c
    ReceiveConfig = 0x134
    ReceiveStatus = 0x135
    PatternMatchData1 = 0x136
    PatternMatchData2 = 0x137
    PatternMatchData3 = 0x138
    RxfSop1 = 0x139
    RxfSop2 = 0x13a
    RxfSop3 = 0x13b
    RxfPat1 = 0x13c # 32 times to 0x15b
    RxfPbm1 = 0x15c # 4 times to 0x15f
    RxfPatternControl = 0x160
    RxfStatus = 0x161
    TenMegSgmiiConfig = 0x16f
    IoMuxConfig = 0x170
    GpioMuxControl = 0x172
    TdrGeneralConfig1 = 0x180
    TdrPeakLoc1 = 0x190 # 10 times to 0x199
    TdrPeakAmp1 = 0x19a # 10 times to 0x1a3
    TdrGeneralStatus = 0x1a4
    ProgGain = 0x1d5

@smi.Interface.db.register("dp83867")
class Dp83867(ethernet_phy.Clause22EthernetPhy):
    def __init__(self, bus, name = "dp83867", phyad = None):
        super().__init__(bus, name = "dp83867", phyad = phyad)

    def reg_set(self, reg, value):
        if reg <= 0x1f:
            return self.write(reg, value)
        else:
            return self.ext_write(0x1f, reg, value)

    def reg_get(self, reg):
        if reg <= 0x1f:
            return self.read(reg)
        else:
            return self.ext_read(0x1f, reg)

