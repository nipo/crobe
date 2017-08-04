from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
import binascii
import struct
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
    DI_BASE = 0x0fe081b0
    
    def __init__(self, dp):
        SoC.__init__(self, "Gecko", dp)

        self.device_identify()

        self.logger.info("MCU UID: %016x", self.uid)

    def device_identify(self):
        self.di_data = self.buses[0].mem_read(self.DI_BASE, self.DI_EMUTEMP)
        
        self.uid, = struct.unpack("<Q", self.di_data[self.DI_UNIQUE:self.DI_UNIQUE+8])
        dev_number, family, prod_ref = struct.unpack("<HBB", self.di_data[self.DI_PART:self.DI_PART+4])
        flash_size, ram_size = struct.unpack("<HH", self.di_data[self.DI_MSIZE:self.DI_MSIZE+4])
        tempgrade, pkgtype, pincount, flash_page_size = \
            struct.unpack("<BBBB", self.di_data[self.DI_MEMINFO:self.DI_MEMINFO+4])
        pkgtype = chr(pkgtype)
        flash_page_size = 2 ** ((flash_page_size + 10) & 0xff)

        name = self.PART_NAMES.get(family, "EFM32[%d]" % family) \
               + str(dev_number) + "F" + str(flash_size)
        if pincount:
            name += pkgtype + str(pincount)

        self.name = name

        if name.startswith("EFR"):
            self.mac = self.di_data[self.DI_EUI48+5:self.DI_EUI48-1:-1]
            self.logger.info("EUI48 HWADDR: %s", ':'.join(["%02x"%x for x in self.mac]))

        if pincount:
            self.logger.info("Package: %s%d", self.PACKAGE_NAMES.get(pkgtype, pkgtype), pincount)
            
        self.child_add(EfmFlash("code", 0, flash_size * 1024, flash_page_size, self))
        self.child_add(BusRam("ram", 0x20000000, ram_size * 1024, self.buses[0]))

    PACKAGE_NAMES = {
        'J': "WLCSP",
        'L': "BGA",
        'M': "QFN",
        'Q': "QFP",
        }
    
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

    DI_EUI48            = 0x028
    DI_CUSTOMINFO       = 0x030
    DI_MEMINFO          = 0x034
    DI_UNIQUE           = 0x040
    DI_MSIZE            = 0x048
    DI_PART             = 0x04C
    DI_DEVINFOREV       = 0x050
    DI_EMUTEMP          = 0x054
