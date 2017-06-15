#

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
