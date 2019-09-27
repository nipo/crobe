from ..arm.coresight.rom_table import RomTable
from ..arm.coresight.scs import Scs
import binascii
import time

class Info:
    DBGMCU_IDCODE = [0xe0042000, 0x40015800]
    uid_blob_addr = None
    flash_size_addr = None
    uid_blob_is_coords = False
    dbgmcu_addr = None
    dbgmcu_init = {}
    gpio = None

    def __init__(self, name, flash_page_size):
        self.name = "STM32" + name
        self.flash_page_size = flash_page_size

    def flash_kb_get(self, soc):
        return soc.buses[0].u32_read(self.flash_size_addr) & 0xffff

    def uid_read(self, soc):
        if self.uid_blob_addr:
            return soc.buses[0].mem_read(self.uid_blob_addr, 12)
        else:
            return b"\x00" * 12

    @classmethod
    def from_soc(cls, soc):
        for addr in cls.DBGMCU_IDCODE:
            mcu_id = soc.buses[0].u32_read(addr)
            soc.logger.info("DBGMCU_IDCODE at 0x%08x: 0x%08x", addr, mcu_id)
            if mcu_id:
                break

        if not mcu_id:
            soc.logger.warning("Bad DBGMCU_IDCODE, using RomTable ID instead")
            rom_tables = soc.buses[0].children_of_class(RomTable)
            if rom_tables:
                mcu_id = rom_tables[0].partid.part_no

        return cls.from_id(soc, mcu_id & 0xfff)

    @classmethod
    def from_id(cls, soc, part):
        part &= 0xfff
        if part == 0x411:
            scs, = soc.buses[0].children_of_class(Scs)
            if "M4" in scs.cpu_name:
                part = 0x433
            else:
                part = 0x10033

        return cls.parts[part]

    def flash_add(self, flash_cb, kb):
        if not self.flash_page_size:
            return

        flash_size = kb * 1024

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
            flash_cb("flash", base + offset, size, page_size)

            offset += size
            remaining -= size

class Rm0038(Info):
    flash_size_addr = 0x1ff8004c
    uid_blob_addr = 0x1ff80050

class Rm0038Cat3(Info):
    flash_size_addr = 0x1ff8004c
    uid_blob_addr = 0x1ff800d0

class InfoL1C34(Rm0038Cat3):
    def flash_kb_get(self, soc):
        if Info.flash_kb_get(self, soc):
            return 256
        return 384

class Rm0008(Info):
    flash_size_addr = 0x1ffff7e0
    uid_blob_addr = 0x1ffff7e8
    dbgmcu_addr = 0xe0042000
    dbgmcu_init = {4: 0x186}

class Rm0091Flash:
    BASE = 0x40022000

    ACR     = BASE + 0x00
    KEYR    = BASE + 0x04
    OPTKEYR = BASE + 0x08
    SR      = BASE + 0x0c
    CR      = BASE + 0x10
    AR      = BASE + 0x14
    OBR     = BASE + 0x1c
    WRPR    = BASE + 0x20

    KEY_RDPRT   = 0x00A5
    KEY_1       = 0x45670123
    KEY_2       = 0xCDEF89AB

    SR_BSY      = 0x00000001
    SR_PGERR    = 0x00000004
    SR_WRPRTERR = 0x00000010
    SR_EOP      = 0x00000020

    CR_PG       = 0x00000001
    CR_PER      = 0x00000002
    CR_MER      = 0x00000004
    CR_OPTPG    = 0x00000010
    CR_OPTER    = 0x00000020
    CR_STRT     = 0x00000040
    CR_LOCK     = 0x00000080
    CR_OPTWRE   = 0x00000200
    CR_OBL_LAUNCH = 0x00002000

    def __init__(self, bus):
        self.bus = bus

    def unlock(self):
        while self.bus.u32_read(self.SR) & self.SR_BSY:
            time.sleep(.01)
        if self.bus.u32_read(self.CR) & self.CR_LOCK:
            self.bus.u32_write(self.KEYR, self.KEY_1)
            self.bus.u32_write(self.KEYR, self.KEY_2)

    def opt_unlock(self):
        self.unlock()
        if not (self.bus.u32_read(self.CR) & self.CR_OPTWRE):
            self.bus.u32_write(self.OPTKEYR, self.KEY_1)
            self.bus.u32_write(self.OPTKEYR, self.KEY_2)

    def lock(self):
        if self.bus.u32_read(self.CR) & self.CR_OPTWRE:
            self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) & ~self.CR_OPTWRE)
        if not (self.bus.u32_read(self.CR) & self.CR_LOCK):
            self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_LOCK)

    def mass_erase(self):
        self.unlock()
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_MER)
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_STRT)
        while self.bus.u32_read(self.SR) & self.SR_BSY:
            time.sleep(.01)
        if self.bus.u32_read(self.SR) & self.SR_EOP:
            self.bus.u32_write(self.SR, self.SR_EOP)
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) & ~self.CR_MER)
        self.lock()

    def opt_erase(self):
        self.unlock()
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_OPTER)
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_STRT)
        while self.bus.u32_read(self.SR) & self.SR_BSY:
            time.sleep(.01)
        if self.bus.u32_read(self.SR) & self.SR_EOP:
            self.bus.u32_write(self.SR, self.SR_EOP)
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) & ~self.CR_OPTER)
        self.lock()

    def reload(self):
        self.bus.u32_write(self.CR, self.bus.u32_read(self.CR) | self.CR_OBL_LAUNCH)
        time.sleep(0.1)

class Rm0360(Info):
    flash_size_addr = 0x1ffff7cc
    dbgmcu_addr = 0x40015800
    dbgmcu_init = {4: 0x6, 8:0x1800}
    gpio = 0x48000000, (0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
                        0x00000000, 0xffffffff)
    flash_class = Rm0091Flash

class Rm0385(Info):
    flash_size_addr = 0x1ff0f442
    uid_blob_addr = 0x1ff0f420
    uid_blob_is_coords = True

class Rm0368(Info):
    flash_size_addr = 0x1fff7a22
    uid_blob_addr = 0x1fff7a10
    uid_blob_is_coords = True

class Rm0410(Info):
    flash_size_addr = 0x1ff0f442
    uid_blob_addr = 0x1ff0f420
    uid_blob_is_coords = True

class Rm0090(Info):
    flash_size_addr = 0x1fff7a22
    uid_blob_addr = 0x1fff7a10
    uid_blob_is_coords = True

class Rm0033(Info):
    flash_size_addr = 0x1fff7a22
    uid_blob_addr = 0x1fff7a10

Info.parts = {
    0: Info("", 0),

    # RM0008
    0x410: Rm0008("F10x/Medium-Density", 1024),
    0x412: Rm0008("F10x/Low-Density",    1024),
    0x414: Rm0008("F10x/High-Density",   2048),
    0x418: Rm0008("F10x/Connectivity",   2048),
    0x430: Rm0008("F10x/XL",             2048),
    # RM0360/RM0091
    0x440: Rm0360("F030x8",              1024),
    0x444: Rm0360("F030x4/6",            1024),
    0x445: Rm0360("F070x6",              1024),
    0x448: Rm0360("F070xB",              2048),
    0x442: Rm0360("F030xC",              2048),
    # RM0038
    0x416: Rm0038("L10x/Cat1",            256),
    0x429: Rm0038("L10x/Cat2",            256),
    0x427: Rm0038Cat3("L10x/Cat356",      256),
    0x437: Rm0038Cat3("L10x/Cat356",      256),
    0x436: InfoL1C34("L10x/Cat34",        256),
    # RM0385
    0x449: Rm0385("F7[45]xxx", [(32, 4), (128, 1), (256, 1)]),
    # RM0410
    0x451: Rm0410("F7[67]xx",               0),
    # RM0090
    0x413: Rm0090("F4xx",                   0),
    0x419: Rm0090("F4xx",                   0),
    # RM0368
    0x433: Rm0368("F401",                   0),
    # RM0033
    0x411: Rm0033("F2xx",                 0),
    # Actual ID is 0x433, but collides with other parts.
    # ID 0x10033 does not exist, it is a hack for code in from_id
    0x10033: Rm0033("F2xx",                 0),
}
