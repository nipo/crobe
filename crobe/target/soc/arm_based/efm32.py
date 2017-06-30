from ....part_id import PartId
from .soc import SoC, StubFlash
import binascii
import struct
from ....memory.region import *
from .puppet_code import efm32_flash_erase, efm32_flash_write

class EfmFlash(StubFlash):
    RANGE_ERASE = efm32_flash_erase
    PAGE_WRITE = efm32_flash_write

    def prepare(self):
        self.soc.buses[0].u32_write(0x400c8084, 0x580e)
        self.soc.buses[0].u32_write(0x400c8020, 0x10)
        while not (self.soc.buses[0].u32_read(0x400c802c) & 0x20):
            pass
        self.soc.buses[0].u32_write(0x400c8084, 0)

@SoC.db.register(PartId(6, 0x73, 0x1),
                 PartId(6, 0x73, 0x81),
                 PartId(6, 0x73, 0x82),
                 PartId(6, 0x73, 0xc1),
                 PartId(6, 0x73, 0xc9),
                 PartId(6, 0x73, 0x101),
                 PartId(6, 0x73, 0x901))
class Gecko(SoC):
    DI_UNIQUE = 0x0fe081f0
    DI_PACKAGE_INFO = 0x0fe081e4
    DI_MEM_INFO = 0x0fe081f8
    DI_PART_INFO = 0x0fe081fc
    
    def __init__(self, dp):
        SoC.__init__(self, "Gecko", dp)

        self.device_identify()

        self.logger.info("MCU UID: %016x", self.uid)

    def device_identify(self):
        self.uid, = struct.unpack("<Q", self.buses[0].mem_read(self.DI_UNIQUE, 8))
        part_info = self.buses[0].u32_read(self.DI_PART_INFO)
        mem_info = self.buses[0].u32_read(self.DI_MEM_INFO)
        pack_info = self.buses[0].u32_read(self.DI_PACKAGE_INFO)

        prod_ref = (part_info >> 24) & 0xff
        family = (part_info >> 16) & 0xff
        dev_number = part_info & 0xffff
        flash_size = mem_info & 0xffff
        ram_size = mem_info >> 16

        name = self.PART_NAMES.get(family, "EFM32[%d]" % family) + str(dev_number) + "F" + str(flash_size)

        self.logger.info("DI_PART_INFO: %08x", part_info)
        
        flash_page_size = 2 ** (((pack_info >> 24) + 10) & 0xff)

        self.child_add(EfmFlash(self, "code", 0, flash_size * 1024, flash_page_size))
        self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_size * 1024))

        self.name = name
        
    PART_NAMES = {
        16: "EFR32MG1P",
        17: "EFR32MG1B",
        18: "EFR32MG1V",
        19: "EFR32BG1P",
        20: "EFR32BG1B",
        21: "EFR32BG1V",
        25: "EFR32FG1B",
        26: "EFR32FG1V",
        28: "EFR32MG12P",
        71: "EFM32G",
        72: "EFM32GG",
        73: "EFM32TG",
        74: "EFM32LG",
        75: "EFM32WG",
        76: "EFM32ZG",
        77: "EFM32HG",
        81: "EFM32PG1B",
        83: "EFM32JG1B",
        120: "EZR32WG",
        121: "EZR32LG",
        122: "EZR32HG",
        }
