from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
import enum

class Reg0(Bitfield):
    all = Field(0, 16)
    lf_cs3 = Field(7, 3)
    lf_r3 = Field(4, 3)
    pll_icp = Field(1, 3)

class PllDiv(Bitfield):
    all = Field(0, 32)
    pll_refdiv = Field(18, 14, offset = 1)
    pll_fbdiv1 = Field(8, 10, offset = 1)
    pll_fbdiv0 = Field(0, 8, offset = 1)

class InputConfig(Bitfield):
    all = Field(0, 16)
    st1_sel_ref = BooleanField(12)
    st1_lor_en = BooleanField(11)
    st1_plllock_en = BooleanField(10)
    st0_sel_ref = BooleanField(9)
    st0_lor_en = BooleanField(8)
    st0_plllock_en = BooleanField(7)
    reset = BooleanField(6, inverted = True)
    sync = BooleanField(5, inverted = True)
    cal = BooleanField(4)
    prescaler_b = MappingField(2, 2, [4, 5, 6, None])
    prescaler_a = MappingField(0, 2, [4, 5, 6, None])

class PowerConfig(Bitfield):
    all = Field(0, 16)
    smux_reshape = BooleanField(15)
    smux_delay = BooleanField(14)
    smux_mode = MappingField(13, 1, ["Auto", "Manual"])
    ref = MappingField(12, 1, ["Primary", "Secondary"])
    pri_div = Field(8, 4, offset = 1)
    sec_selbuf = MappingField(6, 2, ["CML", "LVDS", "LVCMOS", "Crystal"])
    sec_en = BooleanField(5)
    pri_selbuf = MappingField(3, 2, ["CML", "LVDS", "LVCMOS", "LVCMOS"])
    pri_en = BooleanField(2)
    sec_supply = MappingField(1, 1, [1.8, 3.3])
    pri_supply = MappingField(0, 1, [1.8, 3.3])

class Out0123Config(Bitfield):
    all = Field(0, 32)
    sel_drv1 = MappingField(23, 2, ["LVDS", "LVDS", "CML", "PECL"])
    en1 = MappingField(21, 2, ["Off", "On", "Cst0", "Cst1"])
    sel_drv0 = MappingField(19, 2, ["LVDS", "LVDS", "CML", "PECL"])
    en0 = MappingField(17, 2, ["Off", "On", "Cst0", "Cst1"])
    supply_ch = MappingField(16, 1, [1.8, 3.3])
    outdiv = Field(0, 8, offset = 1)

class Out45Config(Bitfield):
    all = Field(0, 48)
    outmux = MappingField(45, 2, ["A", "Primary", "Secondary", None])
    pre_div = MappingField(42, 3, {0: 2, 1: 3, 7:1})
    en_fracdiv = BooleanField(41)
    lvcmos_slew_slow = BooleanField(40)
    lvcmos_n = BooleanField(39)
    lvcmos_p = BooleanField(38)
    sel_drv = MappingField(35, 2, ["LVDS", "LVDS", "LVCMOS", "HCSL"])
    en = MappingField(33, 2, ["Off", "On", "Cst0", "Cst1"])
    supply = MappingField(32, 1, [1.8, 3.3])
    outdiv = Field(20, 8, offset = 1)
    fracdiv = Field(0, 20, offset = 1)

class Out67Config(Bitfield):
    all = Field(0, 48)
    pre_div = MappingField(42, 3, {0: 2, 1: 3, 7:1})
    en_fracdiv = BooleanField(41)
    lvcmos_slew_slow = BooleanField(40)
    lvcmos_n = BooleanField(39)
    lvcmos_p = BooleanField(38)
    sel_drv = MappingField(35, 2, ["LVDS", "LVDS", "LVCMOS", "HCSL"])
    en = MappingField(33, 2, ["Off", "On", "Cst0", "Cst1"])
    supply = MappingField(32, 1, [1.8, 3.3])
    outdiv = Field(20, 8, offset = 1)
    fracdiv = Field(0, 20, offset = 1)

class Status(Bitfield):
    all = Field(0, 16)
    pll_lock = BooleanField(2, inverted = True)
    ref_loss = BooleanField(1)
    ref = MappingField(0, 1, ["Primary", "Secondary"])

class Version(Bitfield):
    all = Field(0, 16)
    vco_version = Field(3, 3)
    die_revision = Field(0, 3)

class Cdcm6208(i2c.Slave):
    reg_map = {
        0: Reg0,
        1: PllDiv,
        3: InputConfig,
        4: PowerConfig,
        5: Out0123Config,
        7: Out0123Config,
        9: Out45Config,
        12: Out45Config,
        15: Out67Config,
        18: Out67Config,
        21: Status,
        40: Version,
    }
    
    def __init__(self, bus, saddr):
        super().__init__(bus, "cdcm6208", saddr)

    def reg_read(self, reg):
        reg = int(reg)
        addr = int(reg).to_bytes(2, "big")

        reg_class = self.reg_map[reg]
        reg_size = reg_class._width // 8

        rdata = self.write_read(addr, reg_size)
        value = int.from_bytes(rdata, "big")
        pretty = reg_class(all = value)

        self.logger.trace("Reg read %d %s: %s", reg, rdata.hex(), pretty)

        return pretty

    def reg_write(self, reg, value):
        reg = int(reg)
        addr = int(reg).to_bytes(2, "big")

        reg_class = self.reg_map[reg]
        reg_size = reg_class._width // 8

        pretty = reg_class(all = int(value))
        data = int(value).to_bytes(reg_size, "big")

        self.logger.trace("Reg write %s %s: %s", reg, data.hex(), pretty)

        self.write(addr + data)

    def start(self):
        for no, klass in self.reg_map.items():
            value = self.reg_read(no)
            self.logger.info("[%d, %r]", no, value)
            
    def state_dump(self, pri = 1e6, sec = 1e6):
        status = self.reg_read(21)
        reg1 = self.reg_read(1)
        reg3 = self.reg_read(3)
        reg4 = self.reg_read(4)
        out01 = self.reg_read(5)
        out23 = self.reg_read(7)
        out4 = self.reg_read(9)
        out5 = self.reg_read(12)
        out6 = self.reg_read(15)
        out7 = self.reg_read(18)

        fpri = (pri / reg4.pri_div) if reg4.pri_en else 0
        fsec = sec if reg4.sec_en else 0
        fref = (fpri if reg4.ref == 'Primary' else fsec) / reg1.pll_refdiv
        fvco = fref * reg1.pll_fbdiv0 * reg1.pll_fbdiv1 * reg3.prescaler_a
        fa = fvco / reg3.prescaler_a
        fb = fvco / reg3.prescaler_b
        f0 = fa / out01.outdiv
        f1 = fa / out01.outdiv
        f2 = fb / out23.outdiv
        f3 = fb / out23.outdiv

        if out4.outmux == "A":
            prediv4 = out4.pre_div
            div4 = (out4.outdiv + ((out4.fracdiv * 2**-20) if out4.en_fracdiv else 0))
            f4 = fa / prediv4 / div4
        elif out4.outmux == "Primary":
            prediv4 = 1
            div4 = 1
            f4 = fpri
        else:
            prediv4 = 1
            div4 = 1
            f4 = fsec

        if out5.outmux == "A":
            prediv5 = out5.pre_div
            div5 = (out5.outdiv + ((out5.fracdiv * 2**-20) if out5.en_fracdiv else 0))
            f5 = fa / prediv5 / div5
        elif out5.outmux == "Primary":
            prediv5 = 1
            div5 = 1
            f5 = fpri
        else:
            prediv5 = 1
            div5 = 1
            f5 = fsec

        prediv6 = out6.pre_div if out6.en_fracdiv else 1
        div6 = (out6.outdiv + ((out6.fracdiv * 2**-20) if out6.en_fracdiv else 0))
        f6 = (fa if out6.sel_drv == "A" else fb) / prediv6 / div6

        prediv7 = out7.pre_div if out7.en_fracdiv else 1
        div7 = (out7.outdiv + ((out7.fracdiv * 2**-20) if out7.en_fracdiv else 0))
        f7 = (fa if out7.sel_drv == "A" else fb) / prediv7 / div7

        print(f"PLL {'locked' if status.pll_lock else 'unlocked'}, reference: {status.ref} ({'lost' if status.ref_loss else 'ok'})")
        print(f"Input frequencies: Primary={metric(pri, 'Hz')}, Secondary={metric(sec, 'Hz')}")
        print(f"Primary: {'On' if reg4.pri_en else 'Off'}, {reg4.pri_selbuf} {reg4.pri_supply}V, div={reg4.pri_div}")
        print(f"Secondary: {'On' if reg4.sec_en else 'Off'}, {reg4.sec_selbuf} {reg4.sec_supply}V")
        print(f"Comparator input: {reg4.ref}, div={reg1.pll_refdiv}, freq={metric(fref, 'Hz')}")
        print(f"Feedback divisor: {reg1.pll_fbdiv0}*{reg1.pll_fbdiv1}")
        print(f"VCO output: {metric(fvco, 'Hz')}")
        print(f"Tree A: div={reg3.prescaler_a}, freq={metric(fa, 'Hz')}")
        print(f"Tree B: div={reg3.prescaler_b}, freq={metric(fb, 'Hz')}")
        print(f"Output0: {out01.en0}, {out01.sel_drv0} {out01.supply_ch}V, A/{out01.outdiv}={metric(f0, 'Hz')}")
        print(f"Output1: {out01.en1}, {out01.sel_drv1} {out01.supply_ch}V, A/{out01.outdiv}={metric(f1, 'Hz')}")
        print(f"Output2: {out23.en0}, {out23.sel_drv0} {out23.supply_ch}V, B/{out23.outdiv}={metric(f2, 'Hz')}")
        print(f"Output3: {out23.en1}, {out23.sel_drv1} {out23.supply_ch}V, B/{out23.outdiv}={metric(f3, 'Hz')}")
        print(f"Output4: {out4.en}, {out4.sel_drv} {out4.supply}V, {out4.outmux}/{prediv4}/{div4}={metric(f4, 'Hz')}")
        print(f"Output5: {out5.en}, {out5.sel_drv} {out5.supply}V, {out5.outmux}/{prediv5}/{div5}={metric(f5, 'Hz')}")
        print(f"Output6: {out6.en}, {out6.sel_drv} {out6.supply}V, B/{prediv6}/{div6}={metric(f6, 'Hz')}")
        print(f"Output7: {out7.en}, {out7.sel_drv} {out7.supply}V, B/{prediv7}/{div7}={metric(f7, 'Hz')}")

    def out_freq_get(self, no, pri = 1e6, sec = 1e6):
        f = [0] * 8

        status = self.reg_read(21)
        reg1 = self.reg_read(1)
        reg3 = self.reg_read(3)
        reg4 = self.reg_read(4)
        out01 = self.reg_read(5)
        out23 = self.reg_read(7)
        out4 = self.reg_read(9)
        out5 = self.reg_read(12)
        out6 = self.reg_read(15)
        out7 = self.reg_read(18)

        fpri = (pri / reg4.pri_div) if reg4.pri_en else 0
        fsec = sec if reg4.sec_en else 0
        fref = (fpri if reg4.ref == 'Primary' else fsec) / reg1.pll_refdiv
        fvco = fref * reg1.pll_fbdiv0 * reg1.pll_fbdiv1 * reg3.prescaler_a
        fa = fvco / reg3.prescaler_a
        fb = fvco / reg3.prescaler_b
        f[0] = fa / out01.outdiv
        f[1] = fa / out01.outdiv
        f[2] = fb / out23.outdiv
        f[3] = fb / out23.outdiv

        if out4.outmux == "A":
            prediv4 = out4.pre_div
            div4 = (out4.outdiv + ((out4.fracdiv * 2**-20) if out4.en_fracdiv else 0))
            f[4] = fa / prediv4 / div4
        elif out4.outmux == "Primary":
            prediv4 = 1
            div4 = 1
            f[4] = fpri
        else:
            prediv4 = 1
            div4 = 1
            f[4] = fsec

        if out5.outmux == "A":
            prediv5 = out5.pre_div
            div5 = (out5.outdiv + ((out5.fracdiv * 2**-20) if out5.en_fracdiv else 0))
            f[5] = fa / prediv5 / div5
        elif out5.outmux == "Primary":
            prediv5 = 1
            div5 = 1
            f[5] = fpri
        else:
            prediv5 = 1
            div5 = 1
            f[5] = fsec

        prediv6 = out6.pre_div if out6.en_fracdiv else 1
        div6 = (out6.outdiv + ((out6.fracdiv * 2**-20) if out6.en_fracdiv else 0))
        f[6] = (fa if out6.sel_drv == "A" else fb) / prediv6 / div6

        prediv7 = out7.pre_div if out7.en_fracdiv else 1
        div7 = (out7.outdiv + ((out7.fracdiv * 2**-20) if out7.en_fracdiv else 0))
        f[7] = (fa if out7.sel_drv == "A" else fb) / prediv7 / div7
        
        return f[no]

@i2c.Interface.db.register("cdcm6208")
def cdcm_get(bus):
    return Cdcm6208(bus, None)
