from .soc import SoC, ArmMPuppet
from ....part_id import PartId
import struct

class ChipInfo:
    def __init__(self, name, flash_kb, sram_kb, sram1_kb, usbram_kb, eeprom_kb):
        self.name = name
        self.flash_kb = flash_kb
        self.sram_kb = sram_kb
        self.sram1_kb = sram1_kb
        self.usbram_kb = usbram_kb
        self.eeprom_kb = eeprom_kb

lpc11u12      = ChipInfo("LPC11U12xxxxx/201",  16,  4, 0, 2, 0)
lpc11u13      = ChipInfo("LPC11U13xxxxx/201",  24,  4, 0, 2, 0)
lpc11u14      = ChipInfo("LPC11U14xxxxx/201",  32,  4, 0, 2, 0)
lpc11u22      = ChipInfo("LPC11U22xxxxx/301",  16,  6, 0, 2, 1)
lpc11u23      = ChipInfo("LPC11U23xxxxx/301",  24,  6, 0, 2, 1)
lpc11u24_301  = ChipInfo("LPC11U23xxxxx/301",  32,  6, 0, 2, 2)
lpc11u24_401  = ChipInfo("LPC11U23xxxxx/301",  32,  8, 0, 2, 4)
lpc11u34_311  = ChipInfo("LPC11U34xxxxx/311",  40,  8, 0, 0, 4)
lpc11u34_421  = ChipInfo("LPC11U34xxxxx/421",  48,  8, 0, 2, 4)
lpc11u35_401  = ChipInfo("LPC11U35xxxxx/401",  64,  8, 0, 2, 4)
lpc11u35_501  = ChipInfo("LPC11U35xxxxx/501",  64,  8, 2, 2, 4)
lpc11u36_401  = ChipInfo("LPC11U36xxxxx/401",  96,  8, 0, 2, 4)
lpc11u37_401  = ChipInfo("LPC11U37xxxxx/401",  128, 8, 0, 2, 4)
lpc11u37h_401 = ChipInfo("LPC11U37Hxxxxx/401", 128, 8, 2, 2, 4)
lpc11u37_501  = ChipInfo("LPC11U37xxxxx/501",  128, 8, 2, 2, 4)
        
chip_info = {
    0x095c802b: lpc11u12,
    0x295c802b: lpc11u12,
    0x097a802b: lpc11u13,
    0x297a802b: lpc11u13,
    0x0998802b: lpc11u14,
    0x2998802b: lpc11u14,
    0x2954402b: lpc11u22,
    0x2972402b: lpc11u23,
    0x2988402b: lpc11u24_301,
    0x2980002b: lpc11u24_401,
    0x0003d440: lpc11u34_311,
    0x0001cc40: lpc11u34_421,
    0x0001bc40: lpc11u35_401,
    0x0000bc40: lpc11u35_501,
    0x00019c40: lpc11u36_401,
    0x00017c40: lpc11u37_401,
    0x00007c44: lpc11u37h_401,
    0x00007c40: lpc11u37_501,
}

class LpcPuppet(ArmMPuppet):
    def iap_call(self, *args):
        params = self.allocate(len(args) * 4)
        params.write(struct.pack("<" + "L" * len(args), *args))
        
        result = self.allocate(4 * 4)

        self.call(0x1fff1ff1, params.address, result.address)

        ret = struct.unpack("<LLLL", result.read(4 * 4))

        self.unallocate(params)
        self.unallocate(result)

        return ret

class Lpc11u(SoC):
    puppet_class = LpcPuppet

    def __init__(self, dp, info):
        SoC.__init__(self, info.name, dp)
        self.info = info
        
        self.child_add(BusFlash("code", 0, info.flash_kb * 1024, 4096, self.buses[0]))
        self.child_add(BusRam("ram", 0x10000000, info.sram_kb * 1024, self.buses[0]))

        uid = self.puppet().iap_call(58)
        self.uid = sum([uid[i] << (i * 32) for i in range(4)])

        self.logger.info("MCU UID: %032x", self.uid)
        
    def puppet(self):
        return LpcPuppet(self)
        
@SoC.db.register(PartId(4, 0x3b, 0x471))
def lcp_ducktyping(dp):
    from ....component.arm.mem_ap import MemAp

    try:
        ap, = dp.children_find(lambda x: isinstance(x, MemAp))
        partid = ap.u32_read(0x400483f4)
    except Exception:
        partid = 0

    if partid in chip_info:
        info = chip_info[partid]
        dp.logger.info("LPC Part ID register 0x%08x matching %s", partid, info.name)
        return Lpc11u(dp, info)

    dp.logger.info("LPC Part ID 0x%08x not matched", partid)

    raise NotImplementedError("Not a known LPC idcode: 0x%08x" % partid)
