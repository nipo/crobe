from ....part_id import PartId
from ....component.arm.coresight.scs import Scs
from ....component.st.stm32 import Info
from .soc import SoC, StubFlash, BusRam
import struct
from .puppet_code import stm32f1

class Stm32f1Flash(StubFlash):
    RANGE_ERASE = stm32f1["flash_erase"]
    PAGE_WRITE = stm32f1["flash_write"]

@SoC.db.register(*[PartId(0, 0x20, did) for did in Info.parts.keys() if did])
class Stm(SoC):
    def __init__(self, dp):
        SoC.__init__(self, "STM32", dp)

        self.info = Info.from_soc(self)
        self.name = self.info.name

        uid_blob = self.info.uid_read(self)
        self.uid = int.from_bytes(uid_blob, byteorder = "little")
        self.logger.info("MCU UID: %024x", self.uid)

        ram_size = self.ram_size_probe(0x20000000, 512 * 1024)
        self.info.flash_add(lambda name, base, size, page: self.child_add(Stm32f1Flash(name, base, size, page, self)),
                            self.info.flash_kb_get(self))

        self.child_add(BusRam("ram", 0x20000000, ram_size, self.buses[0]))

        if self.info.uid_blob_is_coords:
            x, y, no, self.lot_number = struct.unpack("<HHB7s", uid_blob)
            self.wafer_pos = no, x, y
            self.logger.info("Wafer no %d, position %d,%d", *self.wafer_pos)
            self.logger.info("Lot number: %s", self.lot_number)
