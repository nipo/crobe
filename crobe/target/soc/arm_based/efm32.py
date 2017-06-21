from ....part_id import PartId
from .soc import SoC
from ....memory.region import *

@SoC.db.register(PartId(6, 0x73, 0x1),
                 PartId(6, 0x73, 0x81),
                 PartId(6, 0x73, 0x82),
                 PartId(6, 0x73, 0xc9),
                 PartId(6, 0x73, 0x901))
class Gecko(SoC):
    DI_UNIQUE = 0x0fe081f0
    DI_PACKAGE_INFO = 0x0fe081e4
    DI_MEM_INFO = 0x0fe081f8
    DI_PART_INFO = 0x0fe081fc
    
    def __init__(self, dp):
        SoC.__init__(self, "Gecko", dp)

        self.device_identify()

    def device_identify(self):
        self.uid = self.buses[0].mem_read(self.DI_UNIQUE, 8)
        pack_info = self.buses[0].u32_read(self.DI_PART_INFO)
        mem_info = self.buses[0].u32_read(self.DI_MEM_INFO)
        part_info = self.buses[0].u32_read(self.DI_PART_INFO)

        prod_ref = (part_info >> 24) & 0xff
        family = (part_info >> 16) & 0xff
        dev_number = part_info & 0xffff
        flash_size = mem_info & 0xffff
        ram_size = mem_info >> 16

        name = self.PART_NAMES.get(family, "EFM32[%d]" % family) + str(dev_number) + "F" + str(flash_size)

        flash_page_size = 2 ** (((pack_info >> 24) + 10) & 0xff)

        self.child_add(NandFlash(self.buses[0], "code", 0, flash_size * 1024, flash_page_size))
        self.child_add(Ram(self.buses[0], "ram", 0, ram_size * 1024))

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
        75: "EFM32XG",
        76: "EFM32ZG",
        77: "EFM32HG",
        81: "EFM32PG1B",
        83: "EFM32JG1B",
        120: "EZR32WG",
        121: "EZR32LG",
        122: "EZR32HG",
        }
