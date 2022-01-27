from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
import enum

# 0x10 Primary Source and Shutdown Register
# 0x11 VCO Band and Factory Reserved Bits
# 0x12 Crystal X1 Load Capacitor Register
# 0x13 Crystal X2 Load Capacitor Register
# 0x14 Factory Reserved Register
# 0x15 Reference Divider Register
# 0x16 VCO Control Register and Pre-Divider
# 0x17 Feedback Integer Divider Register
# 0x18 Feedback Integer Divider Bits
# 0x19 Feedback Fractional Divider Register
# 0x1A Feedback Fractional Divider Register
# 0x1B Feedback Fractional Divider Register
# 0x1C Factory Reserved Register
# 0x1D Factory Reserved Register
# 0x1E RC Control Register
# 0x1F RC Control Register
# 
# # Stride 0x10
# 0x21 Output Divider Control Register Settings
# 0x22 Output Divider Fractional Settings
# 0x23 Output Divider Fractional Settings
# 0x24 Output Divider Fractional Settings
# 0x25 Output Divider Fractional Settings
# 0x26 Output Divider Step Spread Configuration Register
# 0x27 Output Divider Step Spread Configuration Register
# 0x28 Output Divider Step Spread Configuration Register
# 0x29 Output Divider Spread Modulation Rate Configuration Register
# 0x2A Output Divider Spread Modulation Rate Configuration Register
# 0x2B Output Divider Skew Integer Part
# 0x2C Output Divider Skew Integer Part
# 0x2D Output Divider Integer Part
# 0x2E Output Divider Integer Part
# 0x2F Output Divider Skew Fractional part
# 
# 0x60 Clock 1 Output Configuration
# 0x61 Clock 2 Output Configuration
# 0x62 Clock 1 Output Configuration
# 0x63 Clock 2 Output Configuration
# 0x64 Clock 1 Output Configuration
# 0x65 Clock 2 Output Configuration
# 0x66 Clock 1 Output Configuration
# 0x67 Clock 2 Output Configuration
# 
# 0x68 CLK_OE/Shutdown Function
# 0x69 CLK_OS/Shutdown Function

class ByteSwapField(Field):
    def _swap(self, value):
        return int.from_bytes(int(value).to_bytes(self.width // 8, "little"), "big")

    def extract(self, value):
        return self._swap(super().extract(value))

    def merge(self, register_value, value):
        super().merge(register_value, self._swap(value))

class Power(Bitfield):
    all = Field(0, 8)
    xtal_en = BooleanField(7)
    clkin_en = BooleanField(6)
    vreg_sync = Field(4, 2)
    xtal_double = BooleanField(3)
    refmode_fod = BooleanField(2)
    sd_polarity = BooleanField(1)
    shutdown = BooleanField(0)

class ClkOe(Bitfield):
    all = Field(0, 8)
    clk0_oe = BooleanField(7)
    clk1_oe = BooleanField(6)
    clk2_oe = BooleanField(5)
    clk3_oe = BooleanField(4)
    clk4_oe = BooleanField(3)
    clk0_slew = BooleanField(2)
    clk0_power = MappingField(0, 2, ["3.3v", "1.8v", "2.5v", "none"])

class ClkOs(Bitfield):
    all = Field(0, 8)
    clk0_os = BooleanField(7)
    clk1_os = BooleanField(6)
    clk2_os = BooleanField(5)
    clk3_os = BooleanField(4)
    clk4_os = BooleanField(3)
    clk0_slew = BooleanField(2)
    clk0_power = MappingField(0, 2, ["3.3v", "1.8v", "2.5v", "none"])

class XtalConfig(Bitfield):
    all = Field(0, 24)
    x1_load = Field(18, 6)
    power_sel = MappingField(16, 2, ["manual", "auto-non-revertive", "auto-revertive", "reserved"])
    x2_load = Field(10, 6)
    primsrc = BooleanField(9)
    clkok1024 = BooleanField(8)
    vreg = Field(4, 4)
    res = Field(0, 4)


    power_sel = MappingField(16, 2, ["manual", "auto-non-revertive", "auto-revertive", "reserved"])
    clk3_os = BooleanField(4)
    clk4_os = BooleanField(3)
    clk0_slew = BooleanField(2)
    clk0_power = MappingField(0, 2, ["3.3v", "1.8v", "2.5v", "none"])

class PllConfig(Bitfield):
    all = Field(0, 56)
    # 0x15
    pre_div2 = BooleanField(55)
    pre_div = Field(48, 7)
    # 0x16
    pre_bypass = BooleanField(47)
    dither_gain = Field(44, 3)
    afc_en = BooleanField(43)
    afc_cfg = Field(40, 3)
    # 0x17 - 0x18
    fb_int_div = Field(28, 12)
    sdm_order = Field(26, 2)
    i2c_ssce = BooleanField(25)
    res = BooleanField(24)
    # 0x19
    fb_frac_div = Field(0, 24)

class VcoConfig(Bitfield):
    all = Field(0, 8)
    # 0x11
    vreg_xtal = MappingField(6, 2, ["1.2v", "res", "1.3v", "1.33v"])
    vco_band_test = BooleanField(5)
    vco_band = Field(0, 5)

class FactoryConfig(Bitfield):
    all = Field(0, 16)
    # 0x1c
    calibration_start = BooleanField(15)
    cnf_vreg = Field(13, 2)
    cnf_vreg_vco = Field(11, 2)
    cnf_vreg_bias = Field(9, 2)
    cp_en = BooleanField(8)
    # 0x1d
    cfg_cp = Field(4, 4)
    vco_en = BooleanField(3)
    i2c_global_reset_en = BooleanField(2, inverted = True)
    vco_mon_en = BooleanField(1)
    pll_bias_en = BooleanField(0)

class RcControl(Bitfield):
    all = Field(0, 16)
    # 0x1e
    lpf_cnf_rz = Field(11, 5)
    lpf_cnf_cp = Field(8, 3)
    # 0x1f
    p3_byp = BooleanField(7)
    p3_cnf = Field(1, 6)
    pfd_delay = BooleanField(0)

class DividerConfig(Bitfield):
    all = Field(0, 120)
    # 0x21
    reset = BooleanField(119, inverted = True)
    pi_out_cap = Field(116, 3)
    selb_norm = BooleanField(115)
    sel_ext = BooleanField(114)
    int_mode = BooleanField(113)
    en_fod = BooleanField(112)
    # 0x22 - 0x25
    frac_div = Field(82, 30, signed = True)
    ssce = BooleanField(81)
    # 0x26 - 0x28
    step = ByteSwapField(56, 24)
    # 0x29 - 0x2a
    period = Field(43, 13)
    vreg_fod = Field(42, 1)
    # 41-40:res
    # 0x2b - 0x2c
    skew = Field(28, 12)
    aux_en = BooleanField(24)
    # 0x2d - 0x2e
    int_div = Field(12, 12)
    # 11-8: res
    # 0x2f
    # 7-6: res
    frac_skew = Field(0, 6)

class OutputConfig(Bitfield):
    all = Field(0, 16)
    # 0x60
    cfg = Field(13, 3)
    power = Field(11, 2)
    slew = Field(8, 2)
    # 0x61
    slew_diff = Field(2, 6)
    amuxen2 = BooleanField(1)
    buf_en = BooleanField(0)
    
class Versa6(i2c.Slave):
    reg_map = {
        0x10: Power,
        0x11: VcoConfig,
        0x12: XtalConfig,
        0x15: PllConfig,
        0x1c: FactoryConfig,
        0x1e: RcControl,
        0x21: DividerConfig,
        0x31: DividerConfig,
        0x41: DividerConfig,
        0x51: DividerConfig,
        0x60: OutputConfig,
        0x62: OutputConfig,
        0x64: OutputConfig,
        0x66: OutputConfig,
        0x68: ClkOe,
        0x69: ClkOs,
    }
    
    def __init__(self, bus, saddr):
        super().__init__(bus, "versa6", saddr)

    def reg_read(self, reg):
        reg = int(reg)
        addr = int(reg).to_bytes(1, "big")

        reg_class = self.reg_map[reg]
        reg_size = reg_class._width // 8

        rdata = self.write_read(addr, reg_size)
        value = int.from_bytes(rdata, "big")
        pretty = reg_class(all = value)

        self.logger.debug("Reg read %d %s: %s", reg, rdata.hex(), pretty)

        return pretty

    def reg_write(self, reg, value):
        reg = int(reg)
        addr = int(reg).to_bytes(1, "big")

        reg_class = self.reg_map[reg]
        reg_size = reg_class._width // 8

        pretty = reg_class(all = int(value))
        data = int(value).to_bytes(reg_size, "big")

        self.logger.debug("Reg write %s %s: %s", reg, data.hex(), pretty)

        self.write(addr + data)

    def start(self):
        for no, klass in self.reg_map.items():
            value = self.reg_read(no)
            self.logger.info("[%d, %r]", no, value)
            
    def state_dump(self, clkin = 1e6, xtalin = 1e6):
        power = self.reg_read(0x10)
        vco = self.reg_read(0x11)
        xtal = self.reg_read(0x12)
        pll = self.reg_read(0x15)
        factory = self.reg_read(0x1c)
        rc = self.reg_read(0x1e)
        divider = [self.reg_read(0x21 + 0x10 * i) for i in range(4)]
        output = [self.reg_read(0x60 + 0x02 * i) for i in range(4)]
        oe = self.reg_read(0x68)
        os = self.reg_read(0x69)

        if power.clkin_en:
            ref = clkin
        else:
            ref = xtalin
            if power.xtal_double:
                ref = xtalin * 2
            if not power.xtal_en:
                ref = 0

        if pll.pre_bypass:
            ref2pll = ref
        elif pll.pre_div2:
            ref2pll = ref / 2
        else:
            ref2pll = ref / pll.pre_div

        fb_div = pll.fb_int_div + (pll.fb_frac_div / 2**24)
        vco_freq = ref2pll * fb_div

        print(f"Reference: {metric(ref2pll, 'Hz')} x {fb_div}")
        print(f"VCO Freq: {metric(vco_freq, 'Hz')}")
        for i in range(4):
            if divider[i].en_fod and not divider[i].selb_norm:
                div = divider[i].int_div + divider[i].frac_div / 2 ** 24
                if divider[i].ssce:
                    ssf = divider[i].step * divider[i].period / 2 ** 24
                    div += ssf / 2
                    freq = vco_freq / 2 / (div or 1)
                    fss = freq / 2 / divider[i].period
                    ssamt = ssf / div
                else:
                    freq = vco_freq / 2 / (div or 1)
                    fss = 0
                    ssamt = 0

                print(divider[i])
                print(f"Output {i}, /2/{div}, {metric(freq, 'Hz')} fss={metric(fss, 'Hz')} +- {ssamt*100:2.2f}%")
                continue
            if divider[i].selb_norm and divider[i].sel_ext:
                print(f"Output {i}, same as {i-1}")
                continue
            if not divider[i].en_fod and not divider[i].sel_ext and not divider[i].selb_norm:
                print(f"Output {i}, off")
                continue
            print(f"Output {i}, invalid", divider[i])
                
        
@i2c.Interface.db.register("versa6")
def versa6_get(bus):
    return Versa6(bus, None)
