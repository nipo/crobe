from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
from ...util.prime import prime_factors
import enum
import math

class RegDef:
    def __init__(self, name, address, base, length):
        self.name = name
        self.address = address
        self.base = base
        self.length = length

registers = [
    RegDef("CLKIN_2_CLK_SEL", 0x73, 0, 2),
    RegDef("CLKIN_3_CLK_SEL", 0x74, 0, 2),
    RegDef("DESIGN_ID0", 0x17, 0, 8),
    RegDef("DESIGN_ID1", 0x18, 0, 8),
    RegDef("DESIGN_ID2", 0x19, 0, 8),
    RegDef("DEVICE_GRADE", 0xF, 0, 8),
    RegDef("DEVICE_PN_BASE", 0xD, 0, 8),
    RegDef("DEVICE_REV", 0xE, 0, 8),
    RegDef("FACTORY_OPN_ID0", 0x10, 0, 4),
    RegDef("FACTORY_OPN_ID1", 0x10, 4, 4),
    RegDef("FACTORY_OPN_ID2", 0x11, 4, 4),
    RegDef("FACTORY_OPN_ID3", 0x11, 0, 4),
    RegDef("FACTORY_OPN_ID4", 0x12, 0, 4),
    RegDef("FACTORY_OPN_REVISION", 0x12, 4, 4),
    RegDef("HSDIV0A_DIV", 0x2B, 0, 8),
    RegDef("HSDIV0B_DIV", 0x2C, 0, 8),
    RegDef("HSDIV0_DIV_SEL", 0x35, 0, 1),
    RegDef("HSDIV1A_DIV", 0x2D, 0, 8),
    RegDef("HSDIV1B_DIV", 0x2E, 0, 8),
    RegDef("HSDIV1_DIV_SEL", 0x35, 1, 1),
    RegDef("HSDIV2A_DIV", 0x2F, 0, 8),
    RegDef("HSDIV2B_DIV", 0x30, 0, 8),
    RegDef("HSDIV2_DIV_SEL", 0x35, 2, 1),
    RegDef("HSDIV3A_DIV", 0x31, 0, 8),
    RegDef("HSDIV3B_DIV", 0x32, 0, 8),
    RegDef("HSDIV3_DIV_SEL", 0x35, 3, 1),
    RegDef("HSDIV4A_DIV", 0x33, 0, 8),
    RegDef("HSDIV4B_DIV", 0x34, 0, 8),
    RegDef("HSDIV4_DIV_SEL", 0x35, 4, 1),
    RegDef("I2C_ADDR", 0x21, 0, 7),
    RegDef("I2C_SCL_PUP_ENA", 0x23, 0, 1),
    RegDef("I2C_SDA_PUP_ENA", 0x23, 1, 1),
    RegDef("ID0A_DEN", 0x3A, 0, 15),
    RegDef("ID0A_INTG", 0x36, 0, 15),
    RegDef("ID0A_RES", 0x38, 0, 15),
    RegDef("ID0A_SS_ENA", 0x3C, 0, 1),
    RegDef("ID0A_SS_MODE", 0x3C, 1, 2),
    RegDef("ID0A_SS_STEP_INTG", 0x3F, 0, 12),
    RegDef("ID0A_SS_STEP_NUM", 0x3D, 0, 12),
    RegDef("ID0A_SS_STEP_RES", 0x40, 0, 15),
    RegDef("ID0B_DEN", 0x46, 0, 15),
    RegDef("ID0B_INTG", 0x42, 0, 15),
    RegDef("ID0B_RES", 0x44, 0, 15),
    RegDef("ID0B_SS_ENA", 0x48, 0, 1),
    RegDef("ID0B_SS_MODE", 0x48, 1, 2),
    RegDef("ID0B_SS_STEP_INTG", 0x4B, 0, 12),
    RegDef("ID0B_SS_STEP_NUM", 0x49, 0, 12),
    RegDef("ID0B_SS_STEP_RES", 0x4C, 0, 15),
    RegDef("ID0_CFG_SEL", 0x35, 6, 1),
    RegDef("ID1A_DEN", 0x52, 0, 15),
    RegDef("ID1A_INTG", 0x4E, 0, 15),
    RegDef("ID1A_RES", 0x50, 0, 15),
    RegDef("ID1A_SS_ENA", 0x54, 0, 1),
    RegDef("ID1A_SS_MODE", 0x54, 1, 2),
    RegDef("ID1A_SS_STEP_INTG", 0x57, 0, 12),
    RegDef("ID1A_SS_STEP_NUM", 0x55, 0, 12),
    RegDef("ID1A_SS_STEP_RES", 0x58, 0, 15),
    RegDef("ID1B_DEN", 0x5E, 0, 15),
    RegDef("ID1B_INTG", 0x5A, 0, 15),
    RegDef("ID1B_RES", 0x5C, 0, 15),
    RegDef("ID1B_SS_ENA", 0x60, 0, 1),
    RegDef("ID1B_SS_MODE", 0x60, 1, 2),
    RegDef("ID1B_SS_STEP_INTG", 0x63, 0, 12),
    RegDef("ID1B_SS_STEP_NUM", 0x61, 0, 12),
    RegDef("ID1B_SS_STEP_RES", 0x64, 0, 15),
    RegDef("ID1_CFG_SEL", 0x35, 7, 1),
    RegDef("IDPA_DEN", 0x6B, 0, 15),
    RegDef("IDPA_INTG", 0x67, 0, 15),
    RegDef("IDPA_RES", 0x69, 0, 15),
    RegDef("IMUX_SEL", 0x24, 0, 2),
    RegDef("OMUX0_SEL0", 0x25, 0, 2),
    RegDef("OMUX0_SEL1", 0x25, 4, 3),
    RegDef("OMUX1_SEL0", 0x26, 0, 2),
    RegDef("OMUX1_SEL1", 0x26, 4, 3),
    RegDef("OMUX2_SEL0", 0x27, 0, 2),
    RegDef("OMUX2_SEL1", 0x27, 4, 3),
    RegDef("OMUX3_SEL0", 0x28, 0, 2),
    RegDef("OMUX3_SEL1", 0x28, 4, 3),
    RegDef("OMUX4_SEL0", 0x29, 0, 2),
    RegDef("OMUX4_SEL1", 0x29, 4, 3),
    RegDef("OMUX5_SEL0", 0x2A, 0, 2),
    RegDef("OMUX5_SEL1", 0x2A, 4, 3),
    RegDef("OUT0_CMOS_INV", 0x7D, 4, 2),
    RegDef("OUT0_DIFF_INV", 0x7d, 6, 2),
    RegDef("OUT0_CMOS_SLEW", 0x7E, 0, 2),
    RegDef("OUT0_CMOS_STR", 0x7E, 2, 1),
    RegDef("OUT0_DIV", 0x7B, 0, 6),
    RegDef("OUT0_MODE", 0x7A, 0, 4),
    RegDef("OUT0_OE", 0xB6, 0, 1),
    RegDef("OUT0_SKEW", 0x7C, 0, 3),
    RegDef("OUT0_STOP_HIGHZ", 0x7D, 0, 1),
    RegDef("OUT10_CMOS_INV", 0xAF, 4, 1),
    RegDef("OUT10_DIFF_INV", 0xAF, 6, 1),
    RegDef("OUT10_CMOS_SLEW", 0xB0, 0, 1),
    RegDef("OUT10_CMOS_STR", 0xB0, 2, 1),
    RegDef("OUT10_DIV", 0xAD, 0, 6),
    RegDef("OUT10_MODE", 0xAC, 0, 4),
    RegDef("OUT10_OE", 0xB7, 2, 1),
    RegDef("OUT10_SKEW", 0xAE, 0, 3),
    RegDef("OUT10_STOP_HIGHZ", 0xAF, 0, 1),
    RegDef("OUT11_CMOS_INV", 0xB4, 4, 2),
    RegDef("OUT11_CMOS_SLEW", 0xB5, 0, 1),
    RegDef("OUT11_CMOS_STR", 0xB5, 2, 1),
    RegDef("OUT11_DIFF_INV", 0xB4, 6, 1),
    RegDef("OUT11_DIV", 0xB2, 0, 6),
    RegDef("OUT11_MODE", 0xB1, 0, 4),
    RegDef("OUT11_OE", 0xB7, 3, 1),
    RegDef("OUT11_SKEW", 0xB3, 0, 3),
    RegDef("OUT11_STOP_HIGHZ", 0xB4, 0, 1),
    RegDef("OUT1_CMOS_INV", 0x82, 4, 1),
    RegDef("OUT1_DIFF_INV", 0x82, 6, 1),
    RegDef("OUT1_DIFF_INV", 0x82, 6, 1),
    RegDef("OUT1_CMOS_SLEW", 0x83, 0, 1),
    RegDef("OUT1_CMOS_STR", 0x83, 2, 1),
    RegDef("OUT1_DIV", 0x80, 0, 6),
    RegDef("OUT1_MODE", 0x7F, 0, 4),
    RegDef("OUT1_OE", 0xB6, 1, 1),
    RegDef("OUT1_SKEW", 0x81, 0, 3),
    RegDef("OUT1_STOP_HIGHZ", 0x82, 0, 2),
    RegDef("OUT2_CMOS_INV", 0x87, 4, 1),
    RegDef("OUT2_DIFF_INV", 0x87, 6, 1),
    RegDef("OUT2_CMOS_SLEW", 0x88, 0, 1),
    RegDef("OUT2_CMOS_STR", 0x88, 2, 1),
    RegDef("OUT2_DIV", 0x85, 0, 6),
    RegDef("OUT2_MODE", 0x84, 0, 4),
    RegDef("OUT2_OE", 0xB6, 2, 1),
    RegDef("OUT2_SKEW", 0x86, 0, 3),
    RegDef("OUT2_STOP_HIGHZ", 0x87, 0, 1),
    RegDef("OUT3_CMOS_INV", 0x8C, 4, 1),
    RegDef("OUT3_DIFF_INV", 0x8C, 6, 1),
    RegDef("OUT3_CMOS_SLEW", 0x8D, 0, 2),
    RegDef("OUT3_CMOS_STR", 0x8D, 2, 1),
    RegDef("OUT3_DIV", 0x8A, 0, 6),
    RegDef("OUT3_MODE", 0x89, 0, 4),
    RegDef("OUT3_OE", 0xB6, 3, 1),
    RegDef("OUT3_SKEW", 0x8B, 0, 3),
    RegDef("OUT3_STOP_HIGHZ", 0x8C, 0, 2),
    RegDef("OUT4_CMOS_INV", 0x91, 4, 1),
    RegDef("OUT4_DIFF_INV", 0x91, 6, 1),
    RegDef("OUT4_CMOS_SLEW", 0x92, 0, 1),
    RegDef("OUT4_CMOS_STR", 0x92, 2, 1),
    RegDef("OUT4_DIV", 0x8F, 0, 6),
    RegDef("OUT4_MODE", 0x8E, 0, 4),
    RegDef("OUT4_OE", 0xB6, 4, 1),
    RegDef("OUT4_SKEW", 0x90, 0, 3),
    RegDef("OUT4_STOP_HIGHZ", 0x91, 0, 2),
    RegDef("OUT5_CMOS_INV", 0x96, 4, 1),
    RegDef("OUT5_DIFF_INV", 0x96, 6, 1),
    RegDef("OUT5_CMOS_SLEW", 0x97, 0, 1),
    RegDef("OUT5_CMOS_STR", 0x97, 2, 1),
    RegDef("OUT5_DIV", 0x94, 0, 6),
    RegDef("OUT5_MODE", 0x93, 0, 4),
    RegDef("OUT5_OE", 0xB6, 5, 1),
    RegDef("OUT5_SKEW", 0x95, 0, 3),
    RegDef("OUT5_STOP_HIGHZ", 0x96, 0, 2),
    RegDef("OUT6_CMOS_INV", 0x9B, 4, 1),
    RegDef("OUT6_DIFF_INV", 0x9B, 6, 1),
    RegDef("OUT6_CMOS_SLEW", 0x9C, 0, 1),
    RegDef("OUT6_CMOS_STR", 0x9C, 2, 1),
    RegDef("OUT6_DIV", 0x99, 0, 6),
    RegDef("OUT6_MODE", 0x98, 0, 4),
    RegDef("OUT6_OE", 0xB6, 6, 1),
    RegDef("OUT6_SKEW", 0x9A, 0, 3),
    RegDef("OUT6_STOP_HIGHZ", 0x9B, 0, 1),
    RegDef("OUT7_CMOS_INV", 0xA0, 4, 1),
    RegDef("OUT7_DIFF_INV", 0xA0, 6, 1),
    RegDef("OUT7_CMOS_SLEW", 0xA1, 0, 1),
    RegDef("OUT7_CMOS_STR", 0xA1, 2, 1),
    RegDef("OUT7_DIV", 0x9E, 0, 6),
    RegDef("OUT7_MODE", 0x9D, 0, 4),
    RegDef("OUT7_OE", 0xB6, 7, 1),
    RegDef("OUT7_SKEW", 0x9F, 0, 3),
    RegDef("OUT7_STOP_HIGHZ", 0xA0, 0, 1),
    RegDef("OUT8_CMOS_INV", 0xA5, 4, 1),
    RegDef("OUT8_DIFF_INV", 0xA5, 6, 1),
    RegDef("OUT8_CMOS_SLEW", 0xA6, 0, 1),
    RegDef("OUT8_CMOS_STR", 0xA6, 2, 2),
    RegDef("OUT8_DIV", 0xA3, 0, 6),
    RegDef("OUT8_MODE", 0xA2, 0, 4),
    RegDef("OUT8_OE", 0xB7, 0, 1),
    RegDef("OUT8_SKEW", 0xA4, 0, 3),
    RegDef("OUT8_STOP_HIGHZ", 0xA5, 0, 1),
    RegDef("OUT9_CMOS_INV", 0xAA, 4, 1),
    RegDef("OUT9_DIFF_INV", 0xAA, 6, 1),
    RegDef("OUT9_CMOS_SLEW", 0xAB, 0, 1),
    RegDef("OUT9_CMOS_STR", 0xAB, 2, 1),
    RegDef("OUT9_DIV", 0xA8, 0, 6),
    RegDef("OUT9_MODE", 0xA7, 0, 4),
    RegDef("OUT9_OE", 0xB7, 1, 1),
    RegDef("OUT9_SKEW", 0xA9, 0, 3),
    RegDef("OUT9_STOP_HIGHZ", 0xAA, 0, 1),
    RegDef("PDIV_DIV", 0x75, 0, 5),
    RegDef("PLL_MODE", 0xBE, 2, 4),
    RegDef("UDRV_OE_ENA", 0x8, 0, 1),
    RegDef("USER_SCRATCH0", 0x9, 0, 8),
    RegDef("USER_SCRATCH1", 0xA, 0, 8),
    RegDef("USER_SCRATCH2", 0xB, 0, 8),
    RegDef("USER_SCRATCH3", 0xC, 0, 8),
    RegDef("USYS_CTRL", 0x6, 0, 8),
    RegDef("USYS_START", 0xB8, 0, 8),
    RegDef("USYS_STAT", 0x7, 0, 8),
    RegDef("VDDO_OK", 0x5, 0, 6),
    RegDef("VDD_XTAL_OK", 0x5, 7, 1),
    RegDef("XOSC_DIS", 0xB9, 0, 1),
    RegDef("IBUF0_DIS", 0xB9, 1, 1),
    RegDef("IBUF1_DIS", 0xB9, 2, 1),
    RegDef("IMUX_DIS", 0xB9, 3, 1),
    RegDef("PDIV_DIS", 0xB9, 4, 1),
    RegDef("PLL_DIS", 0xB9, 5, 1),
    RegDef("HSDIV0_DIS", 0xBA, 0, 1),
    RegDef("HSDIV1_DIS", 0xBA, 1, 1),
    RegDef("HSDIV2_DIS", 0xBA, 2, 1),
    RegDef("HSDIV3_DIS", 0xBA, 3, 1),
    RegDef("HSDIV4_DIS", 0xBA, 4, 1),
    RegDef("ID0_DIS", 0xBA, 5, 1),
    RegDef("ID1_DIS", 0xBA, 6, 1),
    RegDef("OMUX0_DIS", 0xBB, 0, 1),
    RegDef("OMUX1_DIS", 0xBB, 1, 1),
    RegDef("OMUX2_DIS", 0xBB, 2, 1),
    RegDef("OMUX3_DIS", 0xBB, 3, 1),
    RegDef("OMUX4_DIS", 0xBB, 4, 1),
    RegDef("OMUX5_DIS", 0xBB, 5, 1),
    RegDef("OUT0_DIS", 0xBC, 0, 1),
    RegDef("OUT1_DIS", 0xBC, 1, 1),
    RegDef("OUT2_DIS", 0xBC, 2, 1),
    RegDef("OUT3_DIS", 0xBC, 3, 1),
    RegDef("OUT4_DIS", 0xBC, 4, 1),
    RegDef("OUT5_DIS", 0xBC, 5, 1),
    RegDef("OUT6_DIS", 0xBC, 6, 1),
    RegDef("OUT7_DIS", 0xBC, 7, 1),
    RegDef("OUT8_DIS", 0xBD, 0, 1),
    RegDef("OUT9_DIS", 0xBD, 1, 1),
    RegDef("OUT10_DIS", 0xBD, 10, 1),
    RegDef("OUT11_DIS", 0xBD, 11, 1),
    RegDef("XOSC_CINT_ENA", 0xBF, 7, 1),
    RegDef("XOSC_CTRIM_XA", 0xC0, 0, 6),
    RegDef("XOSC_CTRIM_XB", 0xC1, 0, 6),
    RegDef("XOSC_CTRIM_XIN", 0xC0, 0, 6),
    RegDef("XOSC_CTRIM_XOUT", 0xC1, 0, 6),
    ]

class RegisterMap(object):
    # (Group No, VDD)
    OUTPUTS = [(0, "A"), (1, "A"), (1, "A"),
               (2, "B"), (2, "B"), (2, "B"),
               (3, "C"), (3, "C"), (3, "C"),
               (4, "D"), (5, "E"), (5, "E")]
    REF_MIN = 10e6
    REF_MAX = 50e6
    VCO_MIN = 2375e6
    VCO_MAX = 2625e6
    HD_DIV_MIN = 8
    HD_DIV_MAX = 255
    ID_DIV_MIN = 10
    ID_DIV_MAX = 255

    isel_modes = ["disabled", "differential", "CMOS DC", "CMOS AC"]
    imux_names = ["disabled", "xosc", "clkin_2", "clkin_3"]
    pll_modes = [
        (0, 0, 0),
        (350, 10, 15),
        (250, 10, 15),
        (175, 10, 15),
        (500, 15, 30),
        (350, 15, 30),
        (250, 15, 30),
        (175, 15, 30),
        (500, 30, 50),
        (350, 30, 50),
        (250, 30, 50),
        (175, 30, 50),
    ]
    omux_sel0_names = ["Raw PLL Ref", "Prescaled PLL Ref", "CLKIN_2", "CLKIN_3"]
    omux_sel1_names = ["HSDIV0", "HSDIV1", "HSDIV2", "HSDIV3", "HSDIV4", "ID0", "ID1", "OMUX_SEL0"]
    out_stop_names = ["Lo-Z", "Hi-Z"]
    out_slew_names = ["fastest", "slow", "slower", "slowest"]
    out_inv_names = ["none", "inverted"]
    out_str_names = ["50Ω", "25Ω"]
    out_mode_names = ["off", "CMOS+", "CMOS-", "CMOS",
                      "LVDS 2.5/3.3V", "LVDS 1.8V", "Fast LVDS 2.5/3.3V", "Fast LVDS 1.8V",
                      "HCSL 50Ω (ext term)", "HCSL 50Ω (int term)", "HCSL 42.5Ω (ext term)", "HCSL 42.5Ω (int term)",
                      "LVPECL", "Res.", "Res.", "Res."]


    __regs = {}
    for r in registers:
        __regs[r.name] = r

    def __init__(self, device):
        self.__device = device
        self.__values = [0] * 256
        self.__dirty = [False] * 256

    def reload(self):
        for i in range(0, 256, 16):
            data = self.__device.read(i, 16)
            self.__values[i:i+16] = data
        self.__dirty = [False] * 256

    def flush(self):
        while any(self.__dirty):
            first = self.__dirty.index(True)
            try:
                last = self.__dirty.index(True, first + 1)
            except ValueError:
                last = first
            if last - first > 15:
                last = first + 15
            self.__device.write(first, self.__values[first : last + 1])
            self.__dirty[first : last + 1] = [False] * (last - first + 1)

    def __getattr__(self, name):
        rd = self.__regs[name.upper()]
        addr = rd.address
        bit_offset = rd.base
        bit_count = rd.length
        byte_count = (bit_offset + bit_count + 7) // 8
        return (int.from_bytes(bytes(self.__values[addr : addr + byte_count]), "big") >> bit_offset) & ((1 << bit_count) - 1)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)

        rd = self.__regs[name.upper()]
        addr = rd.address
        bit_offset = rd.base
        bit_count = rd.length
        byte_count = (bit_offset + bit_count + 7) // 8
        old = int.from_bytes(bytes(self.__values[addr : addr + byte_count]), "big")
        mask = ((1 << bit_count) - 1) << bit_offset
        to_set = value << bit_offset
        new = (mask & to_set) | (~mask & old)
        self.__values[addr : addr + byte_count] = list(new.to_bytes(byte_count, "big"))
        self.__dirty[addr : addr + byte_count] = [True] * byte_count
        
    def raw_set(self, regs):
        for a, v in regs:
            self.__values[a] = v
            self.__dirty[a] = True
        
    def state_dump(self, xosc = 0, clkin_2 = 0, clkin_3 = 0):
        print(f"XOSC: {metric(clkin_2, 'Hz')}{', +8pF,' if self.xosc_cint_ena else ''}, C0={self.xosc_ctrim_xa}, C1={self.xosc_ctrim_xb}")
        print(f"CLKIN_2: {metric(clkin_2, 'Hz')}, {self.isel_modes[self.clkin_2_clk_sel]}")
        print(f"CLKIN_3: {metric(clkin_3, 'Hz')}, {self.isel_modes[self.clkin_3_clk_sel]}")
        imux_freq = [0, xosc, clkin_2, clkin_3][self.imux_sel]
        print(f"IMUX is {self.imux_names[self.imux_sel]}, {metric(imux_freq, 'Hz')}")

        pdiv = self.pdiv_div
        pfd_ref_freq = (imux_freq / pdiv) if pdiv else 0
        print(f"P Div: {pdiv}, PFD Ref freq: {metric(pfd_ref_freq, 'Hz')}")

        pll_mode = self.pll_modes[self.pll_mode]
        pfd_in_range = pll_mode[1] <= (pfd_ref_freq / 1e6) <= pll_mode[2]
        print(f"PLL mode #{self.pll_mode}: BW={pll_mode[0]}kHz, Fmin={pll_mode[1]}MHz, Fmax={pll_mode[2]}MHz, {'in range' if pfd_in_range else 'out of range'}")

        mnmd = self.idpa_intg
        if self.idpa_den:
            mnmd += self.idpa_res / self.idpa_den
        mnmd /= 128
        vco_freq = pfd_ref_freq * mnmd
        vco_in_range = self.VCO_MIN <= vco_freq <= self.VCO_MAX
        print(f"Mn/Md = {mnmd}, VCO Freq = {metric(vco_freq, 'Hz')}, {'in range' if vco_in_range else 'out of range'}")

        ndiv = []
        for i in range(2):
            for slot, bank in enumerate("AB"):
                reg = lambda name: self.__getattr__(f"ID{i}{bank}_{name}")
                den = reg("den")
                intg = reg("intg")
                res = reg("res")
                ss_ena = reg("ss_ena")
                selected = slot == self.__getattr__(f"ID{i}_CFG_SEL")
                div = (intg + ((res / den) if den else 0)) / 128
                freq = (vco_freq / div) if div else 0
                print(f"ID{i}{bank} = VCO / {div} ({intg // 128} + {(intg % 128) * den + res} / {den}) = {metric(freq, 'Hz')}{' *' if selected else ''}{' w/SS (todo)' if ss_ena else ''}")
                if selected:
                    ndiv.append(freq)

        odiv = []
        for i in range(5):
            for slot, bank in enumerate("AB"):
                div = self.__getattr__(f"HSDIV{i}{bank}_DIV")
                selected = slot == self.__getattr__(f"HSDIV{i}_DIV_SEL")
                freq = (vco_freq / div) if div else 0
                print(f"HSDIV{i}{bank} = VCO / {div} = {metric(freq, 'Hz')}{' *' if selected else ''}")
                if selected:
                    odiv.append(freq)

        omux = []
        for i in range(6):
            sel0 = self.__getattr__(f"omux{i}_sel0")
            sel1 = self.__getattr__(f"omux{i}_sel1")
            sel0_name = self.omux_sel0_names[sel0]
            sel0_freq = [imux_freq, pfd_ref_freq, clkin_2, clkin_3][sel0]
            name = sel0_name if sel1 == 7 else self.omux_sel1_names[sel1]
            freq = (odiv + ndiv + [sel0_freq])[sel1]

            print(f"OMUX{i}, Sel={name}, F={metric(freq, 'Hz')}")
            omux.append(freq)

        output = []
        for i, (source, supply) in enumerate(self.OUTPUTS):
            reg = lambda name: self.__getattr__(f"OUT{i}_{name}")
            cmos_inv = self.out_inv_names[reg("cmos_inv")]
            cmos_slew = self.out_slew_names[reg("cmos_slew")]
            cmos_str = self.out_str_names[reg("cmos_str")]
            div = reg("div")
            mode = self.out_mode_names[reg("mode")]
            oe = reg("oe")
            skew = 35 * reg("skew")
            stop_highz = self.out_stop_names[reg("stop_highz")]

            freq = (omux[source] / div) if div else 0

            print(f"OUT{i}, OMUX{source} / {div} = {metric(freq, 'Hz')}, mode={mode}, stop={stop_highz}, skew={skew}ps, oe={'on' if oe else 'off'}, slew={cmos_slew}, inv={cmos_inv}, str={cmos_str}")
        
        
class Si5332(i2c.Slave):
    def __init__(self, bus, saddr):
        super().__init__(bus, "si5332", saddr)
        self.regs = RegisterMap(self)

    def status_get(self):
        data, = self.read(0x7, 1)
        return data
        
    def read(self, base, size):
        rdata = self.write_read([base], size)
        regs = list(rdata)
        self.logger.trace("Reg read @0x%02x: %s", base, [f"{x:#4x}" for x in regs])
        return regs

    def write(self, base, values):
        self.logger.trace("Reg write @0x%02x: %s", base, [f"{x:#4x}" for x in values])
        super().write(bytes([base]) + bytes(values))

    def start(self):
        self.regs.reload()
        r = self.regs

        self.logger.note("Design ID: %02x%02x%02x",
                         r.design_id0,
                         r.design_id1,
                         r.design_id2)

        self.logger.note("Device PN: %02x, Grade: %02x, Rev: %02x",
                         r.device_pn_base,
                         r.device_grade,
                         r.device_rev)

        self.logger.note("Factory ID: %02x%02x%02x%02x%02x rev %02x",
                         r.factory_opn_id0,
                         r.factory_opn_id1,
                         r.factory_opn_id2,
                         r.factory_opn_id3,
                         r.factory_opn_id4,
                         r.factory_opn_revision)

    def commit(self):
        self.write(6, b'\x01')
        self.regs.flush()
        self.write(6, b'\x02')
        
    def state_dump(self, xosc = 0, clkin_2 = 0, clkin_3 = 0):
        self.regs.state_dump(xosc, clkin_2, clkin_3)
                    
@i2c.Interface.db.register("si5332")
def si5332_get(bus):
    return Si5332(bus, None)
