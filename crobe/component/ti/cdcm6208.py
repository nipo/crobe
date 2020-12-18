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

class Reg1(Bitfield):
    all = Field(0, 32)
    pll_refdiv = Field(18, 14, offset = 1)
    pll_fbdiv1 = Field(8, 10, offset = 1)
    pll_fbdiv0 = Field(0, 8, offset = 1)

class Reg3(Bitfield):
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
    prescaler_a = MappingField(2, 2, [4, 5, 6, None])
    prescaler_b = MappingField(0, 2, [4, 5, 6, None])

class Reg4(Bitfield):
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

class Reg5(Bitfield):
    all = Field(0, 32)
    sel_drv1 = MappingField(23, 2, ["LVDS", "LVDS", "CML", "PECL"])
    en1 = MappingField(21, 2, ["Off", "On", "Cst0", "Cst1"])
    sel_drv0 = MappingField(19, 2, ["LVDS", "LVDS", "CML", "PECL"])
    en0 = MappingField(17, 2, ["Off", "On", "Cst0", "Cst1"])
    supply_ch = MappingField(16, 1, [1.8, 3.3])
    outdiv = Field(0, 8, offset = 1)

class Reg9(Bitfield):
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

class Reg15(Bitfield):
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

class Reg21(Bitfield):
    all = Field(0, 16)
    pll_lock = BooleanField(2, inverted = True)
    ref_loss = BooleanField(1)
    ref = MappingField(0, 1, ["Primary", "Secondary"])

class Reg40(Bitfield):
    all = Field(0, 16)
    vco_version = Field(3, 3)
    die_revision = Field(0, 3)

class Cdcm6208(i2c.Slave):
    reg_map = {
        0: Reg0,
        1: Reg1,
        3: Reg3,
        4: Reg4,
        5: Reg5,
        7: Reg5,
        9: Reg9,
        12: Reg9,
        15: Reg15,
        18: Reg15,
        21: Reg21,
        40: Reg40,
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

        self.logger.debug("Reg read %d %s: %s", reg, rdata.hex(), pretty)

        return pretty

    def reg_write(self, reg, value):
        reg = int(reg)
        addr = int(reg).to_bytes(2, "big")

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
            
    def state_dump(self, pri = 1e6, sec = 1e6):
        status = self.reg_read(21)
        reg1 = self.reg_read(1)
        reg3 = self.reg_read(3)
        reg4 = self.reg_read(4)
        reg5 = self.reg_read(5)
        reg7 = self.reg_read(7)
        reg9 = self.reg_read(9)
        reg12 = self.reg_read(12)
        reg15 = self.reg_read(15)
        reg18 = self.reg_read(18)

        fpri = (pri / reg4.pri_div) if reg4.pri_en else 0
        fsec = sec if reg4.sec_en else 0
        fref = (fpri if reg4.ref == 'Primary' else fsec) / reg1.pll_refdiv
        fvco = fref * reg1.pll_fbdiv0 * reg1.pll_fbdiv1 * reg3.prescaler_a
        fa = fvco / reg3.prescaler_a
        fb = fvco / reg3.prescaler_b
        f0 = fa / reg5.outdiv
        f1 = fa / reg5.outdiv
        f2 = fb / reg7.outdiv
        f3 = fb / reg7.outdiv

        if reg9.outmux == "A":
            prediv4 = reg9.pre_div
            div4 = (reg9.outdiv + ((reg9.fracdiv * 2**-20) if reg9.en_fracdiv else 0))
            f4 = fa / prediv4 / div4
        elif reg9.outmux == "Primary":
            prediv4 = 1
            div4 = 1
            f4 = fpri
        else:
            prediv4 = 1
            div4 = 1
            f4 = fsec

        if reg12.outmux == "A":
            prediv5 = reg12.pre_div
            div5 = (reg12.outdiv + ((reg12.fracdiv * 2**-20) if reg12.en_fracdiv else 0))
            f5 = fa / prediv5 / div5
        elif reg12.outmux == "Primary":
            prediv5 = 1
            div5 = 1
            f5 = fpri
        else:
            prediv5 = 1
            div5 = 1
            f5 = fsec

        prediv6 = reg15.pre_div
        div6 = (reg15.outdiv + ((reg15.fracdiv * 2**-20) if reg15.en_fracdiv else 0))
        f6 = fa / prediv6 / div6

        prediv7 = reg18.pre_div
        div7 = (reg18.outdiv + ((reg18.fracdiv * 2**-20) if reg18.en_fracdiv else 0))
        f7 = fa / prediv7 / div7

        print(f"PLL {'locked' if status.pll_lock else 'unlocked'}, reference: {status.ref} ({'lost' if status.ref_loss else 'ok'})")
        print(f"Input frequencies: Primary={metric(pri, 'Hz')}, Secondary={metric(sec, 'Hz')}")
        print(f"Primary: {'On' if reg4.pri_en else 'Off'}, {reg4.pri_selbuf} {reg4.pri_supply}V, div={reg4.pri_div}")
        print(f"Secondary: {'On' if reg4.sec_en else 'Off'}, {reg4.sec_selbuf} {reg4.sec_supply}V")
        print(f"Comparator input: {reg4.ref}, div={reg1.pll_refdiv}, freq={metric(fref, 'Hz')}")
        print(f"Feedback divisor: {reg1.pll_fbdiv0}*{reg1.pll_fbdiv1}")
        print(f"VCO output: {metric(fvco, 'Hz')}")
        print(f"Tree A: div={reg3.prescaler_a}, freq={metric(fa, 'Hz')}")
        print(f"Tree B: div={reg3.prescaler_a}, freq={metric(fb, 'Hz')}")
        print(f"Output0: {reg5.en0}, {reg5.sel_drv0} {reg5.supply_ch}V, A/{reg5.outdiv}={metric(f0, 'Hz')}")
        print(f"Output1: {reg5.en1}, {reg5.sel_drv1} {reg5.supply_ch}V, A/{reg5.outdiv}={metric(f1, 'Hz')}")
        print(f"Output2: {reg7.en0}, {reg7.sel_drv0} {reg7.supply_ch}V, B/{reg7.outdiv}={metric(f2, 'Hz')}")
        print(f"Output3: {reg7.en1}, {reg7.sel_drv1} {reg7.supply_ch}V, B/{reg7.outdiv}={metric(f3, 'Hz')}")
        print(f"Output4: {reg9.en}, {reg9.sel_drv} {reg9.supply}V, {reg9.outmux}/{prediv4}/{div4}={metric(f4, 'Hz')}")
        print(f"Output5: {reg12.en}, {reg12.sel_drv} {reg12.supply}V, {reg12.outmux}/{prediv5}/{div5}={metric(f5, 'Hz')}")
        print(f"Output6: {reg15.en}, {reg15.sel_drv} {reg15.supply}V, B/{prediv6}/{div6}={metric(f6, 'Hz')}")
        print(f"Output7: {reg18.en}, {reg18.sel_drv} {reg18.supply}V, B/{prediv7}/{div7}={metric(f7, 'Hz')}")

@i2c.Interface.db.register("cdcm6208")
def cdcm_get(bus):
    return Cdcm6208(bus, None)
