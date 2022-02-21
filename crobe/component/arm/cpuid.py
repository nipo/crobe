from ...bitfield import *

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

        if partno & 0xf00 == 0xd00:
            part_name = "Cortex-M%d" % (partno & 0xff)

    return "%s %s r%dp%d" % (impl_name, part_name, variant, revision)

def short_name(cpuid):
    implementer = cpuid >> 24
    variant = (cpuid >> 20) & 0xf
    arch = (cpuid >> 16) & 0xf
    partno = (cpuid >> 4) & 0xfff
    revision = cpuid & 0xf

    if implementer == 0x41:
        if partno & 0xf00 == 0xc00:
            cortex_table = {0: "CA%d",
                            1: "CR%d",
                            2: "CM%d",
                            6: "CM%d+",
                            }
            cno = (partno >> 4) & 0xf
            
            if cno in cortex_table:
                return cortex_table[cno] % (partno & 0xf)

        if partno & 0xf00 == 0xd00:
            return "CM%d" % (partno & 0xff)

    return "Part_%02x/%03x" % (implementer, partno)

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
            for i, (d, v) in enumerate(zip(dumpers, values)):
                reg = d(v)
                reg.dump_pretty(output)
                output()

    class PFR0(Bitfield):
        """Processor features 0"""

        all = Field(0, 32)

        RAS          = MappingField(28, 4, {0: "None", 3: "V1"})
        RAS.doc = "Reliability, Availability, and Serviceability Extension"

        ThumbEE      = MappingField(12, 4, {0: "None", 3: "Thumb-2"})

        Acceleration = MappingField(8, 4, {0: "None", 1: "Software", 3: "Thumb-2"})

        State1       = MappingField(4, 4, {0: "None", 1: "Thumb", 3: "Thumb-2"},
                                    doc = "State 1 ISA")

        State0       = MappingField(0, 4, {0: "None", 1: "ARM"},
                                    doc = "State 0 ISA")

    class PFR1(Bitfield):
        """MCU Programmers model"""

        all = Field(0, 32)

        MProgMod   = MappingField(8, 4, {0: "None", 2: "Two stack"},
                                  doc = "M Programmers' model")
        Security   = MappingField(4, 4, {0: "None", 1: "Implemented", 3: "With state handling"},
                                  doc = "Security extension implemented")
        ARMv4_Prog_Model = MappingField(0, 4, {0: "None", 1: "ARMv4"},
        )

    class DFR(Bitfield):

        all = Field(0, 32)

        UDE       = MappingField(28, 4, {0: "None", 1: "Implemented"},
                                 doc = "Unprivileged Debug Extension")
        MCU       = MappingField(20, 4, {0: "None", 1: "Memory mapped", 2:"Halting supported"},
                                 doc = "M-Profile debug architecture")
        Trace_MM  = MappingField(16, 4, {0: "None", 1: "Memory mapped"})
        Trace_Cop = MappingField(12, 4, {0: "None"})
        Core_MM   = MappingField(8, 4, {0: "None", 1: "ARMv4 MM", 4: "ARMv7 MM"})
        Secure    = MappingField(4, 4, {0: "None"})
        Core_Cop  = MappingField(0, 4, {0: "None"})

    class AFR(Bitfield):

        all = Field(0, 32)

        ImpDef0  = Field(0, 4,
                         doc = "Implementation defined")
        ImpDef1  = Field(4, 4,
                         doc = "Implementation defined")
        ImpDef2  = Field(8, 4,
                         doc = "Implementation defined")
        ImpDef3  = Field(12, 4,
                         doc = "Implementation defined")

    class MMFR0(Bitfield):

        all = Field(0, 32)

        InnerShr = Field(28, 4, doc = "Innermost Shareability")
        FSCE     = MappingField(24, 4, {0: "None"})
        AuxReg   = MappingField(20, 4, {0: "None",
                                        1: "ACR only",
                                        2:"AIFSR, ADFSR"},
                                doc = "Auxiliary control registers support")
        TCM      = MappingField(16, 4, {0: "None",
                                        1: "implementation-defined control"},
                                doc = "Tightly coupled memories support")
        ShareLvl = MappingField(12, 4, {0: "One level",
                                        1: "Two levels"},
                                doc            = "Shareability levels")
        OuterShr = MappingField(8, 4, {0: "Non-cacheable",
                                       1: "With HW Coherency",
                                       15: "Ignored"},
                                doc = "Outermost Shareability")
        PMSA     = MappingField(4, 4, {0: "Not supported",
                                       3:"PMSAv7 with subregions"})
        VMSA     = MappingField(0, 4, {0: "Not supported"})

    class MMFR1(Bitfield):

        all = Field(0, 32)

        Branch_Predictor  = MappingField(28, 4, {0: "None"})
        L1_Test_Clean     = MappingField(24, 8, {0: "None"})
        L1_Unified        = MappingField(20, 4, {0: "None"})
        L1_Harvard        = MappingField(16, 4, {0: "None"})
        L1_SetWay_Unified = MappingField(12, 4, {0: "None"})
        L1_SetWay_Harvard = MappingField(8, 4, {0: "None"})
        L1_MVA_Unified    = MappingField(4, 4, {0: "None"})
        L1_MVA_Harvard    = MappingField(0, 4, {0: "None"})

    class MMFR2(Bitfield):

        all = Field(0, 32)

        HW_Access_Flag = MappingField(28, 4, {0: "Not supported"})
        WFI_Stall      = MappingField(24, 4, {0: "Not supported", 1: "Supported"})
        Barriers       = MappingField(20, 4, {0: "Not supported", 2: "DSB, ISB, DMB"})
        TLB_Unified    = MappingField(16, 4, {0: "Not supported"})
        TLB_Harvard    = MappingField(12, 4, {0: "Not supported"})
        L1_Cache       = MappingField(8, 4, {0: "Not supported"})
        L1_Bg_Prefetch = MappingField(4, 4, {0: "Not supported"})
        L1_Fg_Prefetch = MappingField(0, 4, {0: "Not supported"})

    class MMFR3(Bitfield):

        all = Field(0, 32)

        Supersection  = MappingField(28, 4, {0: "Not supported"})
        Coherent_Walk = MappingField(20, 4, {0: "Not supported"})
        Maint_Bcast   = MappingField(12, 4, {0: "Not supported"})
        BPMaint       = MappingField(8, 4, {0: "Not supported",
                                            1: "Invalidate all",
                                            2: "Invalidate by MVA"},
                                     doc = "Branch predictor maintenance")
        CMaintSW      = MappingField(4, 4, {0: "Not supported",
                                            1: "Invalidate/clean"},
                                     doc = "Cache maintenance for set/way")
        CMaintVA      = MappingField(0, 4, {0: "Not supported",
                                            1: "Invalidate/clean"},
                                     doc = "Cache maintenance by address")

    class ISAR0(Bitfield):

        all = Field(0, 32)

        Divide    = MappingField(24, 4, {0: "", 1:"SDIV, UDIV"})
        Debug     = MappingField(20, 4, {0: "", 1:"BKPT"})
        Coproc    = MappingField(16, 4, {0: "",
                                         1:"CDP, LDC, MCR, MRC, STC",
                                         2:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2",
                                         3:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC",
                                         4:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC, MCRR2, MRRC2",
        })
        CmpBranch = MappingField(12, 4, {0: "",
                                         1:"CBNZ, CBZ",
                                         3:"CBNZ, CBZ and non-predicated + low overhead looping"})
        Bitfield  = MappingField(8, 4, {0: "", 1:"BFC, BFI, SBFX, UBFX"})
        Bitcount  = MappingField(4, 4, {0: "", 1:"CLZ"})
        Atomics   = MappingField(0, 4, {0: "", 1:"SWP, SWPB"})

    class ISAR1(Bitfield):

        all = Field(0, 32)

        Jazelle   = MappingField(24, 4, {0: "", 1:"BXJ"}),
        Interwork = MappingField(24, 4, {0: "",
                                         1:"BX",
                                         2: "BX, BLX",
                                         3: "BX, BLX, dp insts"})
        Immediate = MappingField(20, 4, {0: "",
                                         1:"ADDW, MOVW, MOVT, SUBW"})
        If_Then   = MappingField(16, 4, {0: "",
                                         1: "IT"})
        Extend    = MappingField(12, 4, {0: "",
                                         1:"SXTB, SXTH, UXTB, UXTH",
                                         2:"SXTB, SXTH, UXTB, UXTH, SXTAB, SXTAB16, SXTAH, SXTB16, UXTAB, UXTAB16, UXTAH, UXTB16"})
        Except2   = MappingField(8, 4, {0: "",
                                        1: "RFE, SRS, CPS"
        })
        Except1   = MappingField(4, 4, {0: "",
                                        1: "LDM (exc), STM (user)"
        })
        Endian    = MappingField(0, 4, {0: "",
                                        1: "SETEND"
        })

    class ISAR2(Bitfield):

        all = Field(0, 32)

        Reversal       = MappingField(28, 4, {0: "",
                                              1: "REV, REV16, REVSH",
                                              2: "REV, REV16, REVSH, RBIT",
        })
        PSR            = MappingField(24, 4, {0: "",
                                              1: "MSR, MRS",
        })
        MultU          = MappingField(20, 4, {0: "",
                                              1:"UMULL, UMLAL",
                                              2: "UMULL, UMLAL, UMAAL"})
        MultS          = MappingField(16, 4, {0: "",
                                              1:"SMULL, SMLAL",
                                              2: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT",
                                              3: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT, SMLAD, SMLADX, SMLALD, SMLALDX, SMLSD, SMLSDX, SMLSLD, SMLSLDX, SMMLA, SMMLAR, SMMLS, SMMLSR, SMMUL, SMMULR, SMUAD, SMUADX, SMUSD, SMUSDX",
        })
        Mult           = MappingField(12, 4, {0: "MUL",
                                              1:"MUL, MLA",
                                              2:"MUL, MLA, MLS",
        })
        MultiAccessInt = MappingField(8, 4, {0: "",
                                             1:"LDM, STM restartable",
                                             2:"LDM, STM continuable",
        })
        MemHint        = MappingField(4, 4, {0: "",
                                             1:"PLD",
                                             2:"PLD",
                                             3:"PLD, PLI",
                                             4:"PLD, PLI, PLDW",
        })
        LoadStore      = MappingField(0, 4, {0: "",
                                             1:"LDRD, STRD",
                                             2:"Load-Acquire, Store-release, Exclusives",
        })

    class ISAR3(Bitfield):

        all = Field(0, 32)

        ThumbEE   = MappingField(28, 4, {0: ""})
        TrueNOP   = MappingField(24, 4, {0: "",
                                         1:"NOP"})
        ThumbCopy = MappingField(20, 4, {0: "",
                                         1:"MOV.t1"})
        TabBranch = MappingField(16, 4, {0: "",
                                         1:"TBB, TBH",
        })
        SynchPrim = MappingField(12, 4, {0: "",
                                         2: "LDREX[BH], STREX[BH], CLREX"})
        SVC       = MappingField(8, 4, {0: "", 1:"SVC"})
        SIMD      = MappingField(4, 4, {0: "",
                                        1:"SSAT, USAT",
                                        3: "SSAT, USAT + GE-bits, DSP only"})
        Saturate  = MappingField(0, 4, {0: "", 1:"QADD, QDADD, QDSUB, QSUB"})

    class ISAR4(Bitfield):

        all = Field(0, 32)

        SWP            = MappingField(28, 4, {0: ""})
        PSR_M          = MappingField(24, 4, {0: "",
                                              1:"CPS, MRS, MSR"})
        SynchPrim_frac = MappingField(20, 4, {3: "(LDR,STR,CLR)EX[BH]"})
        Barrier        = MappingField(16, 4, {0: "",
                                              1:"DMB, DSB, ISB",
        })
        Writeback      = MappingField(8, 4, {0: "STM, STM, PUSH, POP only",
                                             1:"All v7-M insts"})
        WithShifts     = MappingField(4, 4, {0: "MOV and shift only",
                                             1: "MOV, shift, load, store (lsl 0-3)",
                                             3: "MOV, shift, load, store (lsl 0-3 & constants)",
                                             4: "Full",})
        Unpriv         = MappingField(0, 4, {0: "",
                                             1:"LDRBT, LDRT, STRBT, STRT",
                                             2:"LDR{SB,B,SH,H}T, STR{B,H}T",
        })

    class ISAR5(Bitfield):

        all = Field(0, 32)

        PACBTI = MappingField(20, 4, {0: "Not implemented",
                                      1: "QARMA5",
                                      2: "Implementation defined",
                                      4: "QARMA3"},
                              doc = "Pointer authentication algorithm")

    class MVFR0(Bitfield):

        all = Field(0, 32)

        FPRound               = MappingField(28, 4, {1: "All"})
        Short_vectors         = MappingField(24, 4, {0: "No"})
        FPSqrt                = MappingField(20, 4, {0: "No", 1: "Yes"})
        FPDivide              = MappingField(16, 4, {0: "No", 1: "Yes"})
        FP_Exception_Trapping = MappingField(12, 4, {0: "No"})
        FPDP                  = MappingField(8, 4, {0: "No", 1:"Yes"})
        FPSP                  = MappingField(4, 4, {0: "No", 1: "Yes", 2:"Yes with restrictions"})
        SIMDReg               = MappingField(0, 4, {1:"16x64 bits"})

    class MVFR1(Bitfield):

        all = Field(0, 32)

        FMAC   = MappingField(28, 4, {0: "Not implemented", 1: "Implemented"},
                              doc = "Fused multiply-accumulate")
        FPHP   = MappingField(24, 4, {0: "Not implemented", 1: "HP-SP conversion", 2:"DP-HP-SP conversion"},
                              doc = "Floating-point half-precision")
        FP16   = MappingField(20, 4, {0: "Not implemented", 1: "Implemented"},
                              doc = "Half-precision")
        MVE    = MappingField(8, 4, {0: "Not supported",
                                     1: "Supported with no FP",
                                     2: "Supported with single/half-precision FP"},
                              doc = "M-profile vector extension")
        FPDNaN = MappingField(4, 4, {0: "None", 1: "Supported"},
                              doc = "FP NaN propagation")
        FPFtZ  = MappingField(0, 4, {0: "Not supported",
                                     1:"Full denormalized support"},
                              doc = "FP Flush-to-zero support")

    class MVFR2(Bitfield):

        all = Field(0, 32)

        VFPMisc = MappingField(4, 4, {0: "No",
                                      4: "Min, max, rounding"})

    class CLIDR(Bitfield):

        all = Field(0, 32)

        cache_mode = {0: "None",
                      1: "I",
                      2: "D",
                      3: "Separate I+D",
                      4: "Unified I+D",
        }
        Ctype1 = MappingField(0, 3, cache_mode)
        Ctype2 = MappingField(3, 3, cache_mode)
        Ctype3 = MappingField(6, 3, cache_mode)
        Ctype4 = MappingField(9, 3, cache_mode)
        Ctype5 = MappingField(12, 3, cache_mode)
        Ctype6 = MappingField(15, 3, cache_mode)
        Ctype7 = MappingField(18, 3, cache_mode)
        LoUIS  = Field(21, 3, offset = 1)
        LoC    = Field(24, 3, offset = 1)
        LoUU   = Field(27, 3, offset = 1)
        ICB    = Field(30, 2, doc = "Highest inner cache level")

    class CCSIDR(Bitfield):

        all = Field(0, 32)

        WT            = BooleanField(31)
        WB            = BooleanField(30)
        RA            = BooleanField(29)
        WA            = BooleanField(28)
        NumSets       = Field(13, 15, offset = 1)
        Associativity = Field(3, 10, offset = 1)
        LineSize      = Log2Field(0, 3, log_offset = 2)
