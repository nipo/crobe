from ..arm.coresight.rom_table import RomTable
import binascii

class Info:
    DBGMCU_IDCODE = 0xe0042000

    def __init__(self, name, flash_page_size, flash_size_addr,
                 uid_blob_addr = None, uid_blob_is_coords = False):
        self.name = "STM32" + name
        self.flash_page_size = flash_page_size
        self.flash_size_addr = flash_size_addr
        self.uid_blob_addr = uid_blob_addr
        self.uid_blob_is_coords = uid_blob_is_coords

    def flash_kb_get(self, soc):
        return soc.buses[0].u32_read(self.flash_size_addr) & 0xffff

    def uid_read(self, soc):
        if self.uid_blob_addr:
            return soc.buses[0].mem_read(self.uid_blob_addr, 12)
        else:
            return b"\x00" * 12

    @classmethod
    def from_soc(cls, soc):
        mcu_id = soc.buses[0].u32_read(cls.DBGMCU_IDCODE)
        soc.logger.info("DBGMCU_IDCODE: 0x%08x", mcu_id)

        if not mcu_id:
            soc.logger.warning("Bad DBGMCU_IDCODE, using RomTable ID instead")
            rom_tables = soc.buses[0].children_of_class(RomTable)
            if rom_tables:
                mcu_id = rom_tables[0].partid.part_no

        return cls.from_id(mcu_id & 0xffff)

    @classmethod
    def from_id(cls, part):
        part &= 0xfff
        if part == 0x411:
            scs, = dp.children_of_class(Scs)
            if "M4" in scs.cpu_name:
                part = 0x433
            else:
                part = 0x10033

        return cls.parts.get(part, 0)

    def flash_add(self, flash_cb):
        if not self.flash_page_size:
            return

        flash_size = self.flash_kb_get(soc) * 1024

        if isinstance(self.flash_page_size, int):
            page_sizes = [(self.flash_page_size, None)]
        else:
            page_sizes = [(s * 1024, limit) for (s, limit) in self.flash_page_size]

        base = 0x08000000
        offset = 0
        remaining = flash_size

        while remaining:
            page_size, limit = page_sizes.pop(0)

            assert remaining % page_size == 0

            pages = remaining // page_size
            if limit and limit > pages:
                pages = limit

            size = pages * page_size
            flash_cb("code", base + offset, size, page_size)

            offset += size
            remaining -= size

class InfoL1C34(Info):
    def flash_kb_get(self, soc):
        if Info.flash_kb_get(self, soc):
            return 256
        return 384

Info.parts = {
    0: Info("", 0, 0, 0),

    # RM0008
    0x410: Info("F10x/Medium-Density", 1024, 0x1ffff7e0, 0x1ffff7e8),
    0x412: Info("F10x/Low-Density",    1024, 0x1ffff7e0, 0x1ffff7e8),
    0x413: Info("F10x/High-Density",   2048, 0x1ffff7e0, 0x1ffff7e8),
    0x418: Info("F10x/Connectivity",   2048, 0x1ffff7e0, 0x1ffff7e8),
    0x430: Info("F10x/XL",             2048, 0x1ffff7e0, 0x1ffff7e8),
    # RM0360
    0x440: Info("F030x8",              1024, 0x1ffff7cc),
    0x444: Info("F030x4/6",            1024, 0x1ffff7cc),
    0x445: Info("F070x6",              1024, 0x1ffff7cc),
    0x448: Info("F070xB",              2048, 0x1ffff7cc),
    0x442: Info("F030xC",              2048, 0x1ffff7cc),
    # RM0038
    0x416: Info("L10x/Cat1",            256, 0x1ff8004c, 0x1ff80050),
    0x429: Info("L10x/Cat2",            256, 0x1ff8004c, 0x1ff80050),
    0x427: Info("L10x/Cat356",          256, 0x1ff800cc, 0x1ff800d0),
    0x437: Info("L10x/Cat356",          256, 0x1ff800cc, 0x1ff800d0),
    0x436: InfoL1C34("L10x/Cat34",      256, 0x1ff800cc, 0x1ff800d0),
    # RM0385
    0x449: Info("F7[45]xxx", [(32, 4), (128, 1), (256, 1)], 0x1ff0f442, 0x1ff0f420, True),
    # RM0410
    0x451: Info("F7[67]xx",               0, 0x1ff0f442, 0x1ff0f420, True),
    # RM0090
    0x413: Info("F4xx",                   0, 0x1fff7a22, 0x1fff7a10, True),
    0x419: Info("F4xx",                   0, 0x1fff7a22, 0x1fff7a10, True),
    # RM0368
    0x433: Info("F401",                   0, 0x1fff7a22, 0x1fff7a10, True),
    # RM0033
    0x10033: Info("F2xx",                 0, 0x1fff7a22, 0x1fff7a10),
}
