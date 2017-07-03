from ... import bitfield

def implementer_name(cpuid):
    implementer_table = {
        0x41: "ARM",
        0x44: "DEC",
        0x4d: "Motorola",
        0x51: "Qualcomm",
        0x56: "Mavell",
        0x69: "Intel",
    }

    implementer = cpuid >> 24
    return implementer_table.get(implementer, "Unknown (0x%02x)" % implementer)

def decode(cpuid):
    implementer_table = {
        0x41: "ARM",
        0x44: "DEC",
        0x4d: "Motorola",
        0x51: "Qualcomm",
        0x56: "Mavell",
        0x69: "Intel",
    }

    implementer = cpuid >> 24
    variant = (cpuid >> 20) & 0xf
    arch = (cpuid >> 16) & 0xf
    partno = (cpuid >> 4) & 0xfff
    revision = cpuid & 0xf

    impl_name = implementer_name(cpuid)
    part_name = "Part_%03x" % partno

    if implementer == 0x41:
        if partno & 0xf00 == 0xc00:
            cortex_table = {0: "Cortex-A%d",
                            1: "Cortex-R%d",
                            2: "Cortex-M%d",
                            6: "Cortex-M%d+",
                            }
            cno = (partno >> 4) & 0xf
            
            if cno in cortex_table:
                part_name = cortex_table[cno] % (partno & 0xf)

    return "%s %s r%dp%d" % (impl_name, part_name, variant, revision)

class CpuidDumper(object):
    def __init__(self, scs):
        self.scs = scs

    def dump(self, output):
        for name in ["pfr", "dfr", "afr", "mmfr", "isar", "mvfr", "clidr", "ccsidr"]:
            values = getattr(self.scs, name)
            if isinstance(values, list):
                dumpers = [getattr(self, "%s%d" % (name.upper(), i)) for i in range(len(values))]
            else:
                values = [values]
                dumpers = [getattr(self, name.upper())]
            for d, v in zip(dumpers, values):
                d(v).dump(output)

    class PFR0(bitfield.Register):
        name = "PFR0"
        fields = [
            bitfield.Field("State3", (12, 15), {3: "Thumb-2"}),
            bitfield.Field("State2", (8, 11), {3: "Thumb-2"}),
            bitfield.Field("State1", (4, 7), {3: "Thumb-2"}),
            bitfield.Field("State0", (0, 3), {0: "Not ARM"}),
            ]

    class PFR1(bitfield.Register):
        name = "PFR1"
        fields = [
            bitfield.Field("Programmer's model", (8, 11), {2: "Two stack"}),
            ]

    class DFR(bitfield.Register):
        name = "DFR"
        fields = [
            bitfield.Field("Debug model", (20, 23), {1: "Memory mapped access"}),
            ]

    class AFR(bitfield.Register):
        name = "AFR"
        fields = [
            ]

    class MMFR0(bitfield.Register):
        name = "MMFR0"
        fields = [
            bitfield.Field("Aux regs", (20, 23), {1: "ACR only"}),
            bitfield.Field("TCM", (16, 19), {0: "None", 1: "implementation-defined control"}),
            bitfield.Field("Shareability levels", (12, 15), {0: "One level"}),
            bitfield.Field("Outermost shareability", (8, 11), {0: "Non-cacheable", 15: "Ignored"}),
            bitfield.Field("PMSA support", (4, 7), {0: "Not supported", 3:"PMSAv7 with subregions"}),
            ]

    class MMFR1(bitfield.Register):
        name = "MMFR1"
        fields = [
            ]

    class MMFR2(bitfield.Register):
        name = "MMFR2"
        fields = [
            bitfield.Field("WFI stall", (24, 27), {0: "Not supported", 1: "Supported"}),
            ]

    class MMFR3(bitfield.Register):
        name = "MMFR3"
        fields = [
            ]

    class ISAR0(bitfield.Register):
        name = "ISAR0"
        fields = [
            bitfield.Field("Divide", (24, 27), {0: "", 1:"SDIV, UDIV"}),
            bitfield.Field("Debug", (20, 23), {0: "", 1:"BKPT"}),
            bitfield.Field("Coproc", (16, 19), {0: "",
                                                1:"CDP, LDC, MCR, MRC, STC",
                                                2:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2",
                                                3:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC",
                                                4:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC, MCRR2, MRRC2",
                                                }),
            bitfield.Field("CmpBranch", (12, 15), {0: "", 1:"CBNZ, CBZ"}),
            bitfield.Field("Bitfield", (8, 11), {0: "", 1:"BFC, BFI, SBFX, UBFX"}),
            bitfield.Field("Bitcount", (4, 7), {0: "", 1:"CLZ"}),
            ]

    class ISAR1(bitfield.Register):
        name = "ISAR1"
        fields = [
            bitfield.Field("Interwork", (24, 27), {0: "",
                                                   1:"BX",
                                                   2: "BX, BLX"}),
            bitfield.Field("Immediate", (20, 23), {0: "", 1:"ADDW, MOVW, MOVT, SUBW"}),
            bitfield.Field("If-Then", (16, 19), {0: "",
                                                 1: "IT"
                                                }),
            bitfield.Field("Extend", (12, 15), {0: "",
                                                1:"SXTB, SXTH, UXTB, UXTH",
                                                2:"SXTB, SXTH, UXTB, UXTH, SXTAB, SXTAB16, SXTAH, SXTB16, UXTAB, UXTAB16, UXTAH, UXTB16"}),
            ]

    class ISAR2(bitfield.Register):
        name = "ISAR2"
        fields = [
            bitfield.Field("Reversal", (28, 31), {0: "",
                                                  1: "REV, REV16, REVSH",
                                                  2: "REV, REV16, REVSH, RBIT",
                                                  }),
            bitfield.Field("MultU", (20, 23), {0: "",
                                               1:"UMULL, UMLAL",
                                               2: "UMULL, UMLAL, UMAAL"}),
            bitfield.Field("MultS", (16, 19), {0: "",
                                               1:"SMULL, SMLAL",
                                               2: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT",
                                               3: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT, SMLAD, SMLADX, SMLALD, SMLALDX, SMLSD, SMLSDX, SMLSLD, SMLSLDX, SMMLA, SMMLAR, SMMLS, SMMLSR, SMMUL, SMMULR, SMUAD, SMUADX, SMUSD, SMUSDX",
                                               }),
            bitfield.Field("Mult", (12, 15), {0: "MUL",
                                              1:"MUL, MLA",
                                              2:"MUL, MLA, MLS",
                                              }),
            bitfield.Field("MultiAccessInt", (8, 11), {0: "",
                                              1:"LDM, STM restartable",
                                              2:"LDM, STM continuable",
                                              }),
            bitfield.Field("MemHint", (4, 7), {0: "",
                                              1:"PLD",
                                              2:"PLD",
                                              3:"PLD, PLI",
                                              }),
            bitfield.Field("LoadStore", (0, 3), {0: "",
                                                 1:"LDRD, STRD",
                                                 }),
            ]

    class ISAR3(bitfield.Register):
        name = "ISAR3"
        fields = [
            bitfield.Field("TrueNOP", (24, 27), {0: "",
                                                 1:"NOP"}),
            bitfield.Field("ThumbCopy", (20, 23), {0: "",
                                                   1:"MOV.t1"}),
            bitfield.Field("TabBranch", (16, 19), {0: "",
                                                   1:"TBB, TBH",
                                                   }),
            bitfield.Field("SynchPrim", (12, 15), {}),
            bitfield.Field("SVC", (8, 11), {0: "", 1:"SVC"}),
            bitfield.Field("SIMD", (4, 7), {0: "", 1:"SSAT, USAT", 3: "SSAT, USAT, PKHBT, PKHTB, QADD16, QADD8, QASX, QSUB16, QSUB8, QSAX, SADD16, SADD8, SASX, SEL, SHADD16, SHADD8, SHASX, SHSUB16, SHSUB8, SHSAX, SSAT16, SSUB16, SSUB8, SSAX, SXTAB16, SXTB16, UADD16, UADD8, UASX, UHADD16, UHADD8, UHASX, UHSUB16, UHSUB8, UHSAX, UQADD16, UQADD8, UQASX, UQSUB16, UQSUB8, UQSAX, USAD8, USADA8, USAT16, USUB16, USUB8, USAX, UXTAB16, UXTB16"}),
            bitfield.Field("Saturate", (0, 3), {0: "", 1:"QADD, QDADD, QDSUB, QSUB"}),
            ]

    class ISAR4(bitfield.Register):
        name = "ISAR4"
        fields = [
            bitfield.Field("PSR_M", (24, 27), {0: "",
                                               1:"CPS, MRS, MSR"}),
            bitfield.Field("SynchPrim_frac", (20, 23), {}),
            bitfield.Field("Barrier", (16, 19), {0: "",
                                                 1:"DMB, DSB, ISB",
                                                 }),
            bitfield.Field("Writeback", (8, 11), {0: "STM, STM, PUSH, POP only", 1:"All v7-M insts"}),
            bitfield.Field("WithShifts", (4, 7), {0: "MOV and shift only",
                                                  1: "MOV, shift, load, store (lsl 0-3)",
                                                  3: "MOV, shift, load, store (lsl 0-3 & constants)"}),
            bitfield.Field("Unpriv", (0, 3), {0: "",
                                              1:"LDRBT, LDRT, STRBT, STRT",
                                              2:"LDRBT, LDRT, STRBT, STRT, LDRHT, LDRSBT, LDRSHT, STRHT",
                                              }),
            ]

    class MVFR0(bitfield.Register):
        name = "MVFR0"
        fields = [
            bitfield.Field("Rounding modes", (28, 31), {1: "All"}),
            bitfield.Field("Short vectors", (24, 27), {0: "No"}),
            bitfield.Field("Square root", (20, 23), {0: "No", 1: "Yes"}),
            bitfield.Field("Divide", (16, 19), {0: "No", 1: "Yes"}),
            bitfield.Field("FP Exc trapping", (12, 15), {0: "No"}),
            bitfield.Field("Double prec.", (8, 11), {0: "No", 1:"Yes"}),
            bitfield.Field("Single prec.", (4, 7), {0: "No", 1: "Yes", 2:"Yes with restrictions"}),
            bitfield.Field("SIMD", (0, 3), {1:"16x64 bits"}),
            ]

    class MVFR1(bitfield.Register):
        name = "MVFR1"
        fields = [
            bitfield.Field("FP fused MAC", (28, 31), {1: "Yes"}),
            bitfield.Field("FP HPFP", (24, 27), {1: "HP-SP conversion", 2:"DP-HP-SP conversion"}),
            bitfield.Field("D_NaN mode", (4, 7), {0: "No", 1: "NaN propagation"}),
            bitfield.Field("FtZ mode", (0, 3), {1:"Full denormalized support"}),
            ]

    class MVFR2(bitfield.Register):
        name = "MVFR2"
        fields = [
            bitfield.Field("VFP Misc", (4, 7), {0: "No", 4: "Min, max, rounding"}),
            ]

    class CLIDR(bitfield.Register):
        name = "CLIDR"
        fields = [
            bitfield.Field("Ctype%d"%n, (n*4, n*4+3), {0: "None",
                                              1: "I",
                                              2: "D",
                                              3: "Separate I+D",
                                              4: "Unified I+D",
                                              })
            for n in range(8)] + [
            bitfield.ValueField("Level of Unification Inner Shareable", (21, 23)),
            bitfield.ValueField("Level of Coherency", (24, 26)),
            bitfield.ValueField("Level of Unification Uniprocessor", (27, 29)),
            ]

    class CCSIDR(bitfield.Register):
        name = "CCSIDR"
        fields = [
            bitfield.ValueField("Sets", (13, 27), z_offset = 1),
            bitfield.ValueField("Associativity", (3, 12), z_offset = 1),
            bitfield.Log2ValueField("Line size", (0, 2), log_offset = 2),
            ]
