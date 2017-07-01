from ....part_id import PartId
from ....memory.region import *
from ....component.arm.coresight.scs import Scs
from .soc import SoC, StubFlash
import struct
from .puppet_code import stm32f1_flash_erase, stm32f1_flash_write

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
        return soc.buses[0].u16_read(self.flash_size_addr)

    @classmethod
    def from_soc(cls, soc):
        mcu_id = soc.buses[0].u32_read(cls.DBGMCU_IDCODE)
        part = mcu_id & 0xfff

        if part == 0x411:
            scs, = dp.children_of_class(Scs)
            if "M4" in scs.cpu_name:
                part = 0x433
            else:
                part = 0x1033

        return cls.parts.get(part, 0)

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
    0x416: Info("L10x/Cat1",              0, 0x1ff8004c, 0x1ff80050),
    0x429: Info("L10x/Cat1",              0, 0x1ff8004c, 0x1ff80050),
    0x427: Info("L10x/Cat356",            0, 0x1ff800cc, 0x1ff800d0),
    0x437: Info("L10x/Cat356",            0, 0x1ff800cc, 0x1ff800d0),
    0x436: InfoL1C34("L10x/Cat34",        0, 0x1ff800cc, 0x1ff800d0),
    # RM0385
    0x449: Info("F7[45]xxx",         0, 0x1ff0f442, 0x1ff0f420, True),
    # RM0410
    0x451: Info("F7[67]xx",          0, 0x1ff0f442, 0x1ff0f420, True),
    # RM0090
    0x413: Info("F4xx",              0, 0x1fff7a22, 0x1fff7a10, True),
    0x419: Info("F4xx",              0, 0x1fff7a22, 0x1fff7a10, True),
    # RM0368
    0x433: Info("F401",              0, 0x1fff7a22, 0x1fff7a10, True),
    # RM0033
    0x1033: Info("F2xx",             0, 0x1fff7a22, 0x1fff7a10),
}

class Stm32f1Flash(StubFlash):
    RANGE_ERASE = stm32f1_flash_erase
    PAGE_WRITE = stm32f1_flash_write

@SoC.db.register(*[PartId(0, 0x20, did) for did in Info.parts.keys()])
class Stm(SoC):
    def __init__(self, dp):
        SoC.__init__(self, "STM32", dp)

        self.info = Info.from_soc(self)
        self.name = self.info.name

        if self.info.uid_blob_addr:
            uid_blob = self.buses[0].mem_read(self.info.uid_blob_addr, 12)
        else:
            uid_blob = b"\x00" * 12
        self.uid = int.from_bytes(uid_blob, byteorder = "little")
        self.logger.info("MCU UID: %024x", self.uid)

        flash_size = self.info.flash_kb_get(self)

        ram_size = self.ram_size_probe(0x20000000, 512 * 1024)

        if self.info.flash_page_size and flash_size:
            self.child_add(Stm32f1Flash(self, "code", 0x08000000, 1024 * flash_size,
                                        self.info.flash_page_size))
            self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_size))

        if self.info.uid_blob_is_coords:
            x, y, no, self.lot_number = struct.unpack("<HHB7s", uid_blob)
            self.wafer_pos = no, x, y
            self.logger.info("Wafer no %d, position %d,%d", *self.wafer_pos)
            self.logger.info("Lot number: %s", self.lot_number)
