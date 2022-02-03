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
            for d, v in zip(dumpers, values):
                output(repr(d(v)))

    class PFR0(bitfield.Bitfield):
        ThumbEE      = bitfield.MappingField(12, 4, {0: "None", 3: "Thumb-2"})
        Acceleration = bitfield.MappingField(8, 4, {1: "Software", 3: "Thumb-2"})
        Thumb_ISA    = bitfield.MappingField(4, 4, {0: "None", 1: "Thumb", 3: "Thumb-2"})
        ARM_ISA      = bitfield.MappingField(0, 4, {0: "None", 1: "ARM"})

    class PFR1(bitfield.Bitfield):
        MCU_Prog_Model   = bitfield.MappingField(8, 4, {0: "None", 2: "Two stack"})
        Sec_Ext          = bitfield.MappingField(4, 4, {0: "None"})
        ARMv4_Prog_Model = bitfield.MappingField(0, 4, {0: "None", 1: "ARMv4"})

    class DFR(bitfield.Bitfield):
        MCU       = bitfield.MappingField(20, 4, {0: "None", 1: "Memory mapped"})
        Trace_MM  = bitfield.MappingField(16, 4, {0: "None", 1: "Memory mapped"})
        Trace_Cop = bitfield.MappingField(12, 4, {0: "None"})
        Core_MM   = bitfield.MappingField(8, 4, {0: "None", 1: "ARMv4 MM", 4: "ARMv7 MM"})
        Secure    = bitfield.MappingField(4, 4, {0: "None"})
        Core_Cop  = bitfield.MappingField(0, 4, {0: "None"})

    class AFR(bitfield.Bitfield):
        pass

    class MMFR0(bitfield.Bitfield):
        Innermost_Shareability = bitfield.Field(28, 4)
        FSCE                   = bitfield.MappingField(24, 4, {0: "None"})
        Aux_Regs               = bitfield.MappingField(20, 4, {0: "None", 1: "ACR only", 2:"AIFSR, ADFSR"})
        TCM                    = bitfield.MappingField(16, 4, {0: "None", 1: "implementation-defined control"})
        Shareability_Levels    = bitfield.MappingField(12, 4, {0: "One level"})
        Outermost_Shareability = bitfield.MappingField(8, 4, {0: "Non-cacheable", 15: "Ignored"})
        PMSA                   = bitfield.MappingField(4, 4, {0: "Not supported", 3:"PMSAv7 with subregions"})
        VMSA                   = bitfield.MappingField(0, 4, {0: "Not supported"})

    class MMFR1(bitfield.Bitfield):
        Branch_Predictor  = bitfield.MappingField(28, 4, {0: "None"})
        L1_Test_Clean     = bitfield.MappingField(24, 8, {0: "None"})
        L1_Unified        = bitfield.MappingField(20, 4, {0: "None"})
        L1_Harvard        = bitfield.MappingField(16, 4, {0: "None"})
        L1_SetWay_Unified = bitfield.MappingField(12, 4, {0: "None"})
        L1_SetWay_Harvard = bitfield.MappingField(8, 4, {0: "None"})
        L1_MVA_Unified    = bitfield.MappingField(4, 4, {0: "None"})
        L1_MVA_Harvard    = bitfield.MappingField(0, 4, {0: "None"})

    class MMFR2(bitfield.Bitfield):
        HW_Access_Flag = bitfield.MappingField(28, 4, {0: "Not supported"})
        WFI_Stall      = bitfield.MappingField(24, 4, {0: "Not supported", 1: "Supported"})
        Barriers       = bitfield.MappingField(20, 4, {0: "Not supported", 2: "DSB, ISB, DMB"})
        TLB_Unified    = bitfield.MappingField(16, 4, {0: "Not supported"})
        TLB_Harvard    = bitfield.MappingField(12, 4, {0: "Not supported"})
        L1_Cache       = bitfield.MappingField(8, 4, {0: "Not supported"})
        L1_Bg_Prefetch = bitfield.MappingField(4, 4, {0: "Not supported"})
        L1_Fg_Prefetch = bitfield.MappingField(0, 4, {0: "Not supported"})

    class MMFR3(bitfield.Bitfield):
        Supersection      = bitfield.MappingField(28, 4, {0: "Not supported"})
        Coherent_Walk     = bitfield.MappingField(20, 4, {0: "Not supported"})
        Maint_Bcast       = bitfield.MappingField(12, 4, {0: "Not supported"})
        Branch_Pred       = bitfield.MappingField(8, 4, {0: "Not supported", 2: "Invalidate by MVA"})
        Hier_SetWay_Cache = bitfield.MappingField(4, 4, {0: "Not supported", 1:"Invalidate/clean"})
        Hier_MVA_Cache    = bitfield.MappingField(0, 4, {0: "Not supported", 1:"Invalidate/clean"})

    class ISAR0(bitfield.Bitfield):
        Divide    = bitfield.MappingField(24, 4, {0: "", 1:"SDIV, UDIV"})
        Debug     = bitfield.MappingField(20, 4, {0: "", 1:"BKPT"})
        Coproc    = bitfield.MappingField(16, 4, {0: "",
                                                  1:"CDP, LDC, MCR, MRC, STC",
                                                  2:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2",
                                                  3:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC",
                                                  4:"CDP, LDC, MCR, MRC, STC, CDP2, LDC2, MCR2, MRC2, STC2, MCRR, MRRC, MCRR2, MRRC2",
        })
        CmpBranch = bitfield.MappingField(12, 4, {0: "", 1:"CBNZ, CBZ"})
        Bitfield  = bitfield.MappingField(8, 4, {0: "", 1:"BFC, BFI, SBFX, UBFX"})
        Bitcount  = bitfield.MappingField(4, 4, {0: "", 1:"CLZ"})
        Atomics   = bitfield.MappingField(0, 4, {0: "", 1:"SWP, SWPB"})

    class ISAR1(bitfield.Bitfield):
        Jazelle   = bitfield.MappingField(24, 4, {0: "", 1:"BXJ"}),
        Interwork = bitfield.MappingField(24, 4, {0: "",
                                                  1:"BX",
                                                  2: "BX, BLX",
                                                  3: "BX, BLX, dp insts"})
        Immediate = bitfield.MappingField(20, 4, {0: "",
                                                  1:"ADDW, MOVW, MOVT, SUBW"})
        If_Then   = bitfield.MappingField(16, 4, {0: "",
                                                  1: "IT"
        })
        Extend    = bitfield.MappingField(12, 4, {0: "",
                                                  1:"SXTB, SXTH, UXTB, UXTH",
                                                  2:"SXTB, SXTH, UXTB, UXTH, SXTAB, SXTAB16, SXTAH, SXTB16, UXTAB, UXTAB16, UXTAH, UXTB16"})
        Except2   = bitfield.MappingField(8, 4, {0: "",
                                                 1: "RFE, SRS, CPS"
        })
        Except1   = bitfield.MappingField(4, 4, {0: "",
                                                 1: "LDM (exc), STM (user)"
        })
        Endian    = bitfield.MappingField(0, 4, {0: "",
                                                 1: "SETEND"
        })

    class ISAR2(bitfield.Bitfield):
        Reversal       = bitfield.MappingField(28, 4, {0: "",
                                                       1: "REV, REV16, REVSH",
                                                       2: "REV, REV16, REVSH, RBIT",
        })
        PSR            = bitfield.MappingField(24, 4, {0: "",
                                                       1: "MSR, MRS",
        })
        MultU          = bitfield.MappingField(20, 4, {0: "",
                                                       1:"UMULL, UMLAL",
                                                       2: "UMULL, UMLAL, UMAAL"})
        MultS          = bitfield.MappingField(16, 4, {0: "",
                                                       1:"SMULL, SMLAL",
                                                       2: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT",
                                                       3: "SMULL, SMLAL, SMLABB, SMLABT, SMLALBB, SMLALBT, SMLALTB, SMLALTT, SMLATB, SMLATT, SMLAWB, SMLAWT, SMULBB, SMULBT, SMULTB, SMULTT, SMULWB, SMULWT, SMLAD, SMLADX, SMLALD, SMLALDX, SMLSD, SMLSDX, SMLSLD, SMLSLDX, SMMLA, SMMLAR, SMMLS, SMMLSR, SMMUL, SMMULR, SMUAD, SMUADX, SMUSD, SMUSDX",
        })
        Mult           = bitfield.MappingField(12, 4, {0: "MUL",
                                                       1:"MUL, MLA",
                                                       2:"MUL, MLA, MLS",
        })
        MultiAccessInt = bitfield.MappingField(8, 4, {0: "",
                                                      1:"LDM, STM restartable",
                                                      2:"LDM, STM continuable",
        })
        MemHint        = bitfield.MappingField(4, 4, {0: "",
                                                      1:"PLD",
                                                      2:"PLD",
                                                      3:"PLD, PLI",
                                                      4:"PLD, PLI, PLDW",
        })
        LoadStore      = bitfield.MappingField(0, 4, {0: "",
                                                      1:"LDRD, STRD",
        })

    class ISAR3(bitfield.Bitfield):
        ThumbEE   = bitfield.MappingField(28, 4, {0: ""})
        TrueNOP   = bitfield.MappingField(24, 4, {0: "",
                                                  1:"NOP"})
        ThumbCopy = bitfield.MappingField(20, 4, {0: "",
                                                  1:"MOV.t1"})
        TabBranch = bitfield.MappingField(16, 4, {0: "",
                                                  1:"TBB, TBH",
        })
        SynchPrim = bitfield.MappingField(12, 4, {0: "",
                                                  2: "LDREX[BH], STREX[BH], CLREX"})
        SVC       = bitfield.MappingField(8, 4, {0: "", 1:"SVC"})
        SIMD      = bitfield.MappingField(4, 4, {0: "",
                                                 1:"SSAT, USAT",
                                                 3: "SSAT, USAT, PKHBT, PKHTB, QADD16, QADD8, QASX, QSUB16, QSUB8, QSAX, SADD16, SADD8, SASX, SEL, SHADD16, SHADD8, SHASX, SHSUB16, SHSUB8, SHSAX, SSAT16, SSUB16, SSUB8, SSAX, SXTAB16, SXTB16, UADD16, UADD8, UASX, UHADD16, UHADD8, UHASX, UHSUB16, UHSUB8, UHSAX, UQADD16, UQADD8, UQASX, UQSUB16, UQSUB8, UQSAX, USAD8, USADA8, USAT16, USUB16, USUB8, USAX, UXTAB16, UXTB16"})
        Saturate  = bitfield.MappingField(0, 4, {0: "", 1:"QADD, QDADD, QDSUB, QSUB"})

    class ISAR4(bitfield.Bitfield):
        SWP            = bitfield.MappingField(28, 4, {0: ""})
        PSR_M          = bitfield.MappingField(24, 4, {0: "",
                                                       1:"CPS, MRS, MSR"})
        SynchPrim_frac = bitfield.MappingField(20, 4, {})
        Barrier        = bitfield.MappingField(16, 4, {0: "",
                                                       1:"DMB, DSB, ISB",
        })
        Writeback      = bitfield.MappingField(8, 4, {0: "STM, STM, PUSH, POP only",
                                                      1:"All v7-M insts"})
        WithShifts     = bitfield.MappingField(4, 4, {0: "MOV and shift only",
                                                      1: "MOV, shift, load, store (lsl 0-3)",
                                                      3: "MOV, shift, load, store (lsl 0-3 & constants)",
                                                      4: "Full",})
        Unpriv         = bitfield.MappingField(0, 4, {0: "",
                                                      1:"LDRBT, LDRT, STRBT, STRT",
                                                      2:"LDR{SB,B,SH,H}T, STR{B,H}T",
        })

    class MVFR0(bitfield.Bitfield):
        FP_rounding_modes     = bitfield.MappingField(28, 4, {1: "All"})
        Short_vectors         = bitfield.MappingField(24, 4, {0: "No"})
        Square_root           = bitfield.MappingField(20, 4, {0: "No", 1: "Yes"})
        Divide                = bitfield.MappingField(16, 4, {0: "No", 1: "Yes"})
        FP_Exception_Trapping = bitfield.MappingField(12, 4, {0: "No"})
        Double_precision      = bitfield.MappingField(8, 4, {0: "No", 1:"Yes"})
        Single_precision      = bitfield.MappingField(4, 4, {0: "No", 1: "Yes", 2:"Yes with restrictions"})
        A_SIMD_registers      = bitfield.MappingField(0, 4, {1:"16x64 bits"})

    class MVFR1(bitfield.Bitfield):
        FP_Fused_MAC = bitfield.MappingField(28, 4, {1: "Yes"})
        FP_HPFP      = bitfield.MappingField(24, 4, {1: "HP-SP conversion", 2:"DP-HP-SP conversion"})
        D_NaN_mode   = bitfield.MappingField(4, 4, {0: "No", 1: "NaN propagation"})
        FtZ_mode     = bitfield.MappingField(0, 4, {1:"Full denormalized support"})

    class MVFR2(bitfield.Bitfield):
        VFP_Misc = bitfield.MappingField(4, 4, {0: "No", 4: "Min, max, rounding"})

    class CLIDR(bitfield.Bitfield):
        cache_mode = {0: "None",
                      1: "I",
                      2: "D",
                      3: "Separate I+D",
                      4: "Unified I+D",
        }
        Ctype1 = bitfield.MappingField(0, 3, cache_mode)
        Ctype2 = bitfield.MappingField(3, 3, cache_mode)
        Ctype3 = bitfield.MappingField(6, 3, cache_mode)
        Ctype4 = bitfield.MappingField(9, 3, cache_mode)
        Ctype5 = bitfield.MappingField(12, 3, cache_mode)
        Ctype6 = bitfield.MappingField(15, 3, cache_mode)
        Ctype7 = bitfield.MappingField(18, 3, cache_mode)
        LoUIS  = bitfield.Field(21, 3, offset = 1)
        LoC    = bitfield.Field(24, 3, offset = 1)
        LoUU   = bitfield.Field(27, 7, offset = 1)

    class CCSIDR(bitfield.Bitfield):
        WT            = bitfield.BooleanField(31)
        WB            = bitfield.BooleanField(30)
        RA            = bitfield.BooleanField(29)
        WA            = bitfield.BooleanField(28)
        NumSets       = bitfield.Field(13, 15, offset = 1)
        Associativity = bitfield.Field(3, 10, offset = 1)
        LineSize      = bitfield.Log2Field(0, 3, log_offset = 2)
