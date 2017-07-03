from ....part_id import PartId
from ....memory.region import *
from ....component.arm.coresight.scs import Scs
from ....component.st.stm32 import Info
from .soc import SoC, StubFlash
import struct
from .puppet_code import stm32f1_flash_erase, stm32f1_flash_write

class Stm32f1Flash(StubFlash):
    RANGE_ERASE = stm32f1_flash_erase
    PAGE_WRITE = stm32f1_flash_write

@SoC.db.register(*[PartId(0, 0x20, did) for did in Info.parts.keys() if did])
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
