from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
from ...util.prime import prime_factors
import enum
import math

class Interrupt(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    sys = BooleanField(7)
    lol_b = BooleanField(6)
    lol_a = BooleanField(5)
    los_clkin = BooleanField(4)
    los_xtal = BooleanField(3)
    revid = Field(0, 2)

class Address(Bitfield):
    _endian = "little"
    all = Field(0, 8)
    one = Field(0, 4)
    i2c_address = Field(4, 4)

class OutputEn(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    oe7 = BooleanField(7)
    oe6 = BooleanField(6)
    oe5 = BooleanField(5)
    oe4 = BooleanField(4)
    oe3 = BooleanField(3)
    oe2 = BooleanField(2)
    oe1 = BooleanField(1)
    oe0 = BooleanField(0)

class Source(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    clkin_div = Log2Field(6, 2)
    pllb_src = MappingField(3, 1, ["Xtal", "Clkin"])
    plla_src = MappingField(2, 1, ["Xtal", "Clkin"])

class ClkControl(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    enable = BooleanField(7, inverted = True)
    ms_int = BooleanField(6)
    ms_src = MappingField(5, 1, ["PLLA", "PLLB"])
    inv = BooleanField(4)
    src = MappingField(2, 2, ["Xtal", "Clkin", "MsRef", "Ms"])
    idrv = MappingField(0, 2, ["2mA", "4mA", "6mA", "8mA"])

class ClkDisState(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    DisState3 = MappingField(6, 2, ["Low", "High", "HighZ", "On"])
    DisState2 = MappingField(4, 2, ["Low", "High", "HighZ", "On"])
    DisState1 = MappingField(2, 2, ["Low", "High", "HighZ", "On"])
    DisState0 = MappingField(0, 2, ["Low", "High", "HighZ", "On"])

class Msn(Bitfield):
    _endian = "big"
    all = Field(0, 64)
    p3 = Field(48, 16)
    p1 = Field(24, 18)
    p2 = Field(0, 20)

    def apply(self, freq_in):
        return freq_in / float(self)

    def __float__(self):
        return self.ratio

    @property
    def ratio(self):
        return 4 + (self.p1 + (self.p2 / self.p3) if self.p3 else 0) / 128

    @ratio.setter
    def ratio(self, abc):
        if isinstance(abc, int):
            ratio = float(abc)
        elif isinstance(abc, float):
            ratio = abc
        elif isinstance(abc, tuple):
            a = abc[0]
            try:
                b = abc[1]
            except:
                b = 0

            try:
                c = abc[2]
            except:
                c = 1
            ratio = a+b/c
        else:
             raise ValueError(abc)   
            
#        if not (15 <= ratio <= 90):
#            raise ValueError("Ratio out of bounds")

        bratio = (ratio - 4) * 128

        rint = int(bratio)
        frac = bratio - rint
        from fractions import Fraction
        f = Fraction(bratio - rint).limit_denominator(2 ** 19)
        
        self.p1 = rint
        self.p2, self.p3 = f.numerator, f.denominator
    
class Ms(Bitfield):
    _endian = "big"
    all = Field(0, 64)
    p3h = Field(20, 4)
    p3l = Field(48, 16)
    divby4 = MappingField(42, 2, [False, "Res1", "Res2", True])
    div = Log2Field(44, 2)
    p1 = Field(24, 18)
    p2 = Field(0, 20)

    @property
    def p3(self):
        return (self.p3h << 16) | self.p3l

    @p3.setter
    def p3(self, value):
        self.p3l = value & 0xffff
        self.p3h = value >> 16
    
    def __float__(self):
        return self.ratio

    @property
    def ratio(self):
        if self.divby4 is True:
            return 4.

        c = self.p3
        b = self.p2 / 128
        a = self.p1 / 128 + 4

        return a + b / (c or 1)

    @ratio.setter
    def ratio(self, abc):
        if isinstance(abc, int):
            ratio = float(abc)
        elif isinstance(abc, float):
            ratio = abc
        elif isinstance(abc, tuple):
            a = abc[0]
            try:
                b = abc[1]
            except:
                b = 0

            try:
                c = abc[2]
            except:
                c = 1
            ratio = a+b/c
        else:
             raise ValueError(abc)   

        if ratio == 4:
            self.divby4 = True
            self.p1 = 0
            self.p2, self.p3 = 0, 1
            return

        self.divby4 = False
         
        if not (4 <= ratio <= 2048):
            raise ValueError("Ratio out of bounds")

        bratio = (ratio - 4) * 128

        rint = int(bratio)
        frac = bratio - rint
        from fractions import Fraction
        f = Fraction(bratio - rint).limit_denominator(2 ** 19)

        self.p1 = rint
        self.p2, self.p3 = f.numerator, f.denominator

class Ms67(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    p1 = Field(0, 8)
    
    def __float__(self):
        return self.ratio

    @property
    def ratio(self):
        return float(self.p1 & ~1)

    @ratio.setter
    def ratio(self, abc):
        if isinstance(abc, int):
            ratio = float(abc)
        elif isinstance(abc, float):
            ratio = abc
        elif isinstance(abc, tuple):
            a = abc[0]
            try:
                b = abc[1]
            except:
                b = 0

            try:
                c = abc[2]
            except:
                c = 1
            ratio = a+b/c
        else:
             raise ValueError(abc)   
            
        if not (6 <= ratio <= 254):
            raise ValueError("Ratio out of bounds")

        if ratio != int(ratio):
            raise ValueError("Can only do integer ratios")

        ratio = int(ratio)

        if ratio & 1:
            raise ValueError("Can only do even ratios")

        self.p1 = ratio
    
class Ss(Bitfield):
    _endian = "big"
    all = Field(0, 104)
    ssc_en = BooleanField(103)
    ssdn_p2 = Field(88, 15)
    ssc_mode = BooleanField(87)
    ssdn_p3 = Field(72, 15)
    ssdn_p1l = Field(64, 8)
    ssudph = Field(60, 4)
    ssdn_p1h = Field(56, 4)
    ssudpl = Field(48, 8)
    ssup_p2 = Field(32, 15)
    ssup_p3 = Field(16, 15)
    ssup_p1l = Field(8, 8)
    ss_nclk = Field(4, 4)
    ssup_p1h = Field(0, 4)

class Vcxo(Bitfield):
    """
    Warning: This one is little-endian
    """
    _endian = "little"
    all = Field(0, 24)
    param = Field(0, 22)

class Phase(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    phoff = Field(0, 7)

class Reset(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    plla_rst = BooleanField(5)
    pllb_rst = BooleanField(7)
    res = Field(0, 4)

class Crystal(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    cl = Field(6, 2)

class Fanout(Bitfield):
    _endian = "big"
    all = Field(0, 8)
    ms = BooleanField(4)
    xo = BooleanField(4)
    clkin = BooleanField(4)

class RegAddr(enum.IntEnum):
    Status = 0
    IntSticky = 1
    IntMask = 2
    Oeb = 3
    Address = 7
    OebMask = 9
    ClkIn = 15
    Clk0 = 16
    Clk1 = 17
    Clk2 = 18
    Clk3 = 19
    Clk4 = 20
    Clk5 = 21
    Clk6 = 22
    Clk7 = 23
    ClkState0 = 24
    ClkState1 = 25
    MsnA = 26
    MsnB = 34
    Ms0 = 42
    Ms1 = 50
    Ms2 = 58
    Ms3 = 66
    Ms4 = 74
    Ms5 = 82
    Ms6 = 90
    Ms7 = 91
    Ss = 92
    Vcxo = 162
    Clk0PhOff = 165
    Clk1PhOff = 166
    Clk2PhOff = 167
    Clk3PhOff = 168
    Clk4PhOff = 169
    Clk5PhOff = 170
    Reset = 177
    Crystal = 183
    Fanout = 187
    
class Si5351(i2c.Slave):
    reg_map = {
        RegAddr.Status: Interrupt,
        RegAddr.IntSticky: Interrupt,
        RegAddr.IntMask: Interrupt,
        RegAddr.Address: Address,
        RegAddr.Oeb: OutputEn,
        RegAddr.OebMask: OutputEn,
        RegAddr.ClkIn: Source,
        RegAddr.Clk0: ClkControl,
        RegAddr.Clk1: ClkControl,
        RegAddr.Clk2: ClkControl,
        RegAddr.Clk3: ClkControl,
        RegAddr.Clk4: ClkControl,
        RegAddr.Clk5: ClkControl,
        RegAddr.Clk6: ClkControl,
        RegAddr.Clk7: ClkControl,
        RegAddr.ClkState0: ClkDisState,
        RegAddr.ClkState1: ClkDisState,
        RegAddr.MsnA: Msn,
        RegAddr.MsnB: Msn,
        RegAddr.Ms0: Ms,
        RegAddr.Ms1: Ms,
        RegAddr.Ms2: Ms,
        RegAddr.Ms3: Ms,
        RegAddr.Ms4: Ms,
        RegAddr.Ms5: Ms,
        RegAddr.Ms6: Ms67,
        RegAddr.Ms7: Ms67,
        RegAddr.Ss: Ss,
        RegAddr.Vcxo: Vcxo,
        RegAddr.Clk0PhOff: Phase,
        RegAddr.Clk1PhOff: Phase,
        RegAddr.Clk2PhOff: Phase,
        RegAddr.Clk3PhOff: Phase,
        RegAddr.Clk4PhOff: Phase,
        RegAddr.Clk5PhOff: Phase,
        RegAddr.Reset: Reset,
        RegAddr.Crystal: Crystal,
        RegAddr.Fanout: Fanout,
    }        
    
    def __init__(self, bus, saddr):
        super().__init__(bus, "si5351", saddr)
        
    def reg_read(self, reg):
        reg = RegAddr(int(reg))
        addr = bytes([int(reg)])

        reg_class = self.reg_map[reg]
        reg_size = reg_class._width // 8

        rdata = self.write_read(addr, reg_size)
        value = int.from_bytes(rdata, reg_class._endian)
        pretty = reg_class(value)

        self.logger.trace("Reg read %d %s: %s", reg, rdata.hex(), pretty)

        return pretty

    @classmethod
    def reg_write_data(cls, reg, value):
        reg = RegAddr(int(reg))
        addr = bytes([int(reg)])

        reg_class = cls.reg_map[reg]
        reg_size = reg_class._width // 8
        data = int(value).to_bytes(reg_size, reg_class._endian)

        return reg, addr, data
        
    def reg_write(self, reg, value):
        reg, addr, data = self.reg_write_data(reg, value)
        reg_class = self.reg_map[reg]
        pretty = reg_class(int(value))
        self.logger.trace("Reg write %s %s: %s", addr, data.hex(), pretty)
        self.write(addr + data)

    #def start(self):
    #    for no, klass in self.reg_map.items():
    #        value = self.reg_read(no)
    #        raw = int(value).to_bytes(value._width // 8, value._endian)
    #        self.logger.info("%s (%s) %r", no, raw.hex(), value)
            
    def state_dump(self, clkin = 0, xtal = 0):
        cur = {}
        for no, klass in self.reg_map.items():
            value = self.reg_read(no)
            cur[no] = value

        sync_a = not cur[RegAddr.Status].lol_a
        sync_b = not cur[RegAddr.Status].lol_b
        ckin_pres = not cur[RegAddr.Status].los_clkin
        xtal_pres = not cur[RegAddr.Status].los_xtal

        self.config_dump(clkin, xtal, cur, sync_a, sync_b, ckin_pres, xtal_pres)

    @classmethod
    def config_dump(cls, clkin, xtal, cur, sync_a = None, sync_b = None, ckin_pres = None, xtal_pres = None):
        oe = set(i for i in range(8) if not ((1 << i) & int(cur[RegAddr.Oeb])))

        clkin_div = cur[RegAddr.ClkIn].clkin_div
        clkin_divided = clkin / clkin_div
        plla_src = clkin_divided if cur[RegAddr.ClkIn].plla_src == "Clkin" else xtal
        pllb_src = clkin_divided if cur[RegAddr.ClkIn].pllb_src == "Clkin" else xtal

        plla_ratio = float(cur[RegAddr.MsnA])
        pllb_ratio = float(cur[RegAddr.MsnB])

        plla_out = plla_src * plla_ratio
        pllb_out = pllb_src * pllb_ratio

        print(f"Clkin freq = {metric(clkin, 'Hz')} / {clkin_div} = {metric(clkin_divided, 'Hz')}")
        print(f"Xtal freq = {metric(xtal, 'Hz')}")
        print(f"PLLA source: {cur[RegAddr.ClkIn].plla_src} x {plla_ratio}", end = "")
        if sync_a is not None:
            print(f", {'locked' if sync_a else 'unlocked'}, {metric(plla_out, 'Hz')}")
        else:
            print()
        print(f"PLLB source: {cur[RegAddr.ClkIn].pllb_src} x {pllb_ratio}", end = "")
        if sync_b is not None:
            print(f", {'locked' if sync_b else 'unlocked'}, {metric(pllb_out, 'Hz')}")
        else:
            print()

        ms_out = [0] * 8
        for i in range(8):
            ms_addr = getattr(RegAddr, f'Ms{i}')
            ms = cur[ms_addr]
            control_addr = getattr(RegAddr, f'Clk{i}')
            control = cur[control_addr]
            ms_input = plla_out if control.ms_src == 'PLLA' else pllb_out

            print(f"Channel{i}")

            ratio = float(ms)
            int_only = control.ms_int or i >= 6
            if int_only:
                ratio = int(ratio)
            output = ms_input / (ratio or 1)
            ms_out[i] = output
            print(f"  MS{i} {'on' if control.enable else 'off'}, {control.ms_src} {'//' if int_only else '/'} {int(ms.ratio) if int_only else float(ms)} = {metric(output, 'Hz')}")

            if control.src == "Xtal":
                src = "Xtal"
                src_freq = xtal
            elif control.src == "Clkin":
                src = "Clkin"
                src_freq = clkin_divided
            elif control.src == "MsRef":
                src = f"MS{i & ~3}"
                src_freq = ms_out[i & ~3]
            else:
                src = f"MS{i}"
                src_freq = output

            out_freq = src_freq / (ms.div if i < 6 else 1)
            print(f"  Output {src} / {ms.div if i < 6 else 1}: {metric(out_freq, 'Hz')}")
            print(f"  Pin {'enabled' if i in oe else 'disabled'}")

@i2c.Interface.db.register("si5351")
def si5351_get(bus):
    return Si5351(bus, None)
