from .. import ethernet_phy
from ...protocol import smi
from ...bitfield import *
from ...util.pretty import metric
from ...util.bit import *
from ...util.timeout import *
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

    # Total number of received bytes
    BistControl1 = 0x71
    # 10: Pkt Count overflow
    # 9: Byte Count overflow
    # 7-0: Error count
    BistControl2 = 0x72
    # BIST Packet length
    BistControl3 = 0x7b
    # BIST IPG
    BistControl4 = 0x7c

    # [xxTR]
    RgmiiDelay = 0x86
    PllControl = 0xc6
    SgmiiControl1 = 0xd3

    # This one is mostly undocumented. It is defined as
    # default = 0x9f22, with no explaination. Nonetheless, SNLA242
    # says this should be set to 0xdf22 to get SFD detection.
    # Simple guess: Bit 14 is SFD Detect enable, but may also be some
    # precondition to SFD detection
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
    # See DP83869 datasheet for complete info
    TdrGeneralConfig1 = 0x180
    TdrGeneralConfig2 = 0x181
    TdrSegDuration1 = 0x182
    TdrSegDuration2 = 0x183
    TdrGeneralConfig3 = 0x184
    TdrGeneralConfig4 = 0x185
    TdrPeakLoc1 = 0x190 # 10 times to 0x199
    TdrPeakAmp1 = 0x19a # 10 times to 0x1a3
    TdrGeneralStatus = 0x1a4
    TdrPeakSign = 0x1a5 # 2 times to 0x1a6
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

    def __tdr_stats_gather(self):
        loc = []
        amp = []
        sign = []

        for i in range(10):
            loc.append(self.reg_get(Register.TdrPeakLoc1 + i))
            amp.append(self.reg_get(Register.TdrPeakAmp1 + i))
        for i in range(2):
            sign.append(self.reg_get(Register.TdrPeakSign + i))
        status = self.reg_get(Register.TdrGeneralStatus)

        loc = b''.join(x.to_bytes(2, "little") for x in loc)
        amp = b''.join(x.to_bytes(2, "little") for x in amp)
        sign = b''.join(x.to_bytes(2, "little") for x in sign)
        
        peaks = []
        for c, name in enumerate("ABCD"):
            high = bool(bit_get(status, c))
            more = bool(bit_get(status, 4 + c))
            cross = bool(bit_get(status, 8 + c))

            for p in range(5):
                l = loc[c * 5 + p]
                a = amp[c * 5 + p] & 0x7f
                if bit_get(sign[c//2], (c & 1) * 5 + p):
                    a = -a

                if l == 0:
                    continue

                m = self.__tdr_loc_m(l)
                peak = Peak(channel = name,
                            location = l,
                            amplitude = a)
                peak.__maybe_cross = cross
                peaks.append(peak)
        return peaks

    def __tdr_start(self, cross = True):
        self.reg_set(Register.Reset, 0x8000)
        self.reg_set(Register.Control, 0x0140)
        self.reg_set(Register.MasterSlaveControl, 0x1000);
        self.reg_set(Register.PhyControl, 0xa24d);
        self.reg_set(Register.TestModeChannel, 0x0480);
        self.reg_set(Register.Config4, 0x0010);
        self.reg_set(Register.Reset, 0x4000)
        self.reg_set(Register.TdrGeneralConfig1, 0x075f if cross else 0x0f5f);
        self.reg_set(Register.TdrGeneralConfig2, 0xf050);
        self.reg_set(Register.TdrGeneralConfig3, 0xe976);
        self.reg_set(Register.TdrGeneralConfig4, 0x19cf);
        self.reg_set(Register.Config3, 1);

    def __tdr_is_done(self):
        return bit_get(self.reg_get(Register.Config3), 1)

    def __tdr_loc_m(self, loc):
        if True:
            il = loc * 0.8621 - 8
            fl = il + (.7 - il) / 100
            return fl
        else:
            fl = loc * 0.822 - 12.55
            return fl

    def tdr_execute(self):
        self.__tdr_start(cross = False)
        while retry_for(3):
            if self.__tdr_is_done():
                break
        no_cross = self.__tdr_stats_gather()

        self.__tdr_start(cross = True)
        while retry_for(3):
            if self.__tdr_is_done():
                break
        with_cross = self.__tdr_stats_gather()

        self.logger.info("Without cross: %s", no_cross)
        self.logger.info("With cross: %s", with_cross)

        for i in range(len(with_cross) - 1, -1, -1):
            x = with_cross[i]
            if not x.__maybe_cross:
                continue
            found = False
            for y in no_cross:
                if y.channel != x.channel:
                    continue
                if abs(y.amplitude - x.amplitude) > 16:
                    continue
                if abs(y.location - x.location) > 2:
                    continue
                found = True
                break
            if found:
                del with_cross[i]
        for x in with_cross:
            x.cross = x.__maybe_cross
        cross = [x for x in with_cross if x.cross]
        return no_cross + cross

class Peak:
    def __init__(self, channel, location, amplitude, cross = False):
        self.channel = channel
        self.location = location
        self.amplitude = amplitude
        self.cross = cross

    def __str__(self):
        return f"Chan {self.channel}: {self.amplitude} @ {metric(self.location, 'm')} {'cross' if self.cross else ''}"

    def __repr__(self):
        return str(self)
