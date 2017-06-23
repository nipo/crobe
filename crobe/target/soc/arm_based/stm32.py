from ....part_id import PartId
from ....memory.region import *
from ....component.arm.coresight.scs import Scs
from .soc import SoC
import struct

class Stm(SoC):
    UID_BLOB_IS_COORDS = False
    LINEUP_NAME = "STM32"
    UID_BLOB = 0

    def __init__(self, dp):
        SoC.__init__(self, self.LINEUP_NAME, dp)

        if self.UID_BLOB:
            uid_blob = self.buses[0].mem_read(self.UID_BLOB, 12)
        else:
            uid_blob = b"\x00" * 12
        self.uid = int.from_bytes(uid_blob, byteorder = "little")
        self.logger.info("MCU UID: %024x", self.uid)

        # FIXME: Retrieve flash page size
        self.child_add(NandFlash(self.buses[0], "code", 0, 1024 * self.stm_flash_kb_get(), 1024))

        if self.UID_BLOB_IS_COORDS:
            x, y, no, self.lot_number = struct.unpack("<HHB7s", uid_blob)
            self.wafer_pos = no, x, y
            self.logger.info("Wafer no %d, position %d,%d", *self.wafer_pos)
            self.logger.info("Lot number: %s", self.lot_number)

    def stm_flash_kb_get(self):
        return self.buses[0].u16_read(self.FLASH_SIZE)

#RM0368
@SoC.db.register(PartId(0, 0x20, 0x433),
                 PartId(0, 0x20, 0x433))
class Stm32Rm0368(Stm):
    FLASH_SIZE = 0x1fff7a22
    UID_BLOB = 0x1fff7a10
    UID_BLOB_IS_COORDS = True
    LINEUP_NAME = "STM32F401"

#RM0033
class Stm32Rm0033(Stm):
    FLASH_SIZE = 0x1fff7a22
    UID_BLOB = 0x1fff7a10
    LINEUP_NAME = "STM32F2xx"

@SoC.db.register(PartId(0, 0x20, 0x411))
def duck_typing_411(dp):
    scs, = dp.children_of_class(Scs)
    if "M4" in scs.cpu_name:
        return Stm32Rm0368(dp)
    return Stm32Rm0033(dp)

# RM0385
@SoC.db.register(PartId(0, 0x20, 0x449))
class Stm32Rm0385(Stm):
    FLASH_SIZE = 0x1ff0f442
    UID_BLOB = 0x1ff0f420
    UID_BLOB_IS_COORDS = True
    LINEUP_NAME = "STM32F7[45]xx"

# RM0410
@SoC.db.register(PartId(0, 0x20, 0x451))
class Stm32Rm0410(Stm):
    FLASH_SIZE = 0x1ff0f442
    UID_BLOB = 0x1ff0f420
    UID_BLOB_IS_COORDS = True
    LINEUP_NAME = "STM32F7[67]xx"

# RM0090
@SoC.db.register(PartId(0, 0x20, 0x413),
                 PartId(0, 0x20, 0x419))
class Stm32Rm0090(Stm):
    FLASH_SIZE = 0x1fff7a22
    UID_BLOB = 0x1fff7a10
    UID_BLOB_IS_COORDS = True
    LINEUP_NAME = "STM32F4xx"

# RM0008
@SoC.db.register(PartId(0, 0x20, 0x410),
                 PartId(0, 0x20, 0x412),
                 PartId(0, 0x20, 0x414),
                 PartId(0, 0x20, 0x418),
                 PartId(0, 0x20, 0x430))
class Stm32Rm0008(Stm):
    FLASH_SIZE = 0x1ffff7e0
    UID_BLOB = 0x1ffff7e8
    LINEUP_NAME = "STM32F10x"

# RM0360
@SoC.db.register(PartId(0, 0x20, 0x440),
                 PartId(0, 0x20, 0x444),
                 PartId(0, 0x20, 0x445),
                 PartId(0, 0x20, 0x448),
                 PartId(0, 0x20, 0x442))
class Stm32Rm0360(Stm):
    FLASH_SIZE = 0x1ffff7cc
    LINEUP_NAME = "STM32F0x0"

# RM0038
@SoC.db.register(PartId(0, 0x20, 0x416),
                 PartId(0, 0x20, 0x429))
class Stm32Rm0038(Stm):
    FLASH_SIZE = 0x1ff8004c
    UID_BLOB = 0x1ff80050
    LINEUP_NAME = "STM32L10x/Cat1"

@SoC.db.register(PartId(0, 0x20, 0x427),
                 PartId(0, 0x20, 0x437))
class Stm32Rm0038_2(Stm32Rm0038):
    FLASH_SIZE = 0x1ff800cc
    UID_BLOB = 0x1ff800d0
    LINEUP_NAME = "STM32L10x/Cat356"

@SoC.db.register(PartId(0, 0x20, 0x436))
class Stm32Rm0038_3(Stm32Rm0038_2):
    LINEUP_NAME = "STM32L10x/Cat34"

    def stm_flash_kb_get(self):
        if Stm32Rm0038_2.stm_flash_kb_get(self):
            return 256
        return 384
