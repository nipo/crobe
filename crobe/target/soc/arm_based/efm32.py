from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
import binascii
import struct
import time
from .puppet_code import efm32series0g, efm32series0, efm32series1, efm32series1gg

class EfmFlash(StubFlash):

    MSC_LOCK_MAGIC = 0x1b71
    MSC_WRITECTRL = 0x8
    MSC_WRITECMD = 0xc
    MSC_WRITECMD_ERASEMAIN0 = 1 << 8
    MSC_WRITECMD_ERASEMAIN1 = 1 << 9
    MSC_WRITECMD_ERASEPAGE = 1 << 1
    MSC_WRITECMD_LADDRIM = 1 << 0
    MSC_WRITECMD_WRITEONCE = 1 << 3
    MSC_WDATA = 0x18
    MSC_STATUS = 0x1c
    MSC_STATUS_BUSY = 0x1
    MSC_MASSLOCK = 0x54
    MSC_MASSLOCK_MAGIC = 0x631a
    MSC_ADDRB = 0x10

    def msc_unlock(self):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_LOCK, self.MSC_LOCK_MAGIC)

    def msc_lock(self):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_LOCK, 0)

    def msc_mass_unlock(self):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_MASSLOCK, self.MSC_MASSLOCK_MAGIC)

    def msc_mass_lock(self):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_MASSLOCK, 0)

    def mass_erase(self):
        self.msc_unlock()
        self.msc_mass_unlock()
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECTRL, 1)
        while self.soc.buses[0].u32_read(self.MSC | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            time.sleep(.01)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEMAIN0)
        while self.soc.buses[0].u32_read(self.MSC | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            time.sleep(.01)
        if self.soc.flash_size >= 2**19:  # read-while-write devices have 512k or more flash
            self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEMAIN1)
            while self.soc.buses[0].u32_read(self.MSC | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
                time.sleep(.01)
        self.msc_mass_lock()
        self.msc_lock()
        self.is_blank = True

    def _word_write(self, addr, value):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECTRL, 1)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_ADDRB, addr)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_LADDRIM)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WDATA, value)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_WRITEONCE)
        while self.soc.buses[0].u32_read(self.MSC | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            pass

    def _page_erase(self, page):
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECTRL, 1)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_ADDRB, page)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_LADDRIM)
        self.soc.buses[0].u32_write(self.MSC | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEPAGE)
        while self.soc.buses[0].u32_read(self.MSC | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            pass

class EfmFlashSeries0G(EfmFlash):
    RANGE_ERASE = efm32series0g["flash_erase"]
    PAGE_WRITE = efm32series0g["flash_write"]

    MSC_LOCK = 0x3c
    MSC = 0x400C0000

    def mass_erase(self):
        self.logger.warning("No mass erase on unprotected EFM32G, erasing main pages...")
        self.erase(0, self.soc.flash_size)

class EfmFlashSeries0(EfmFlash):
    RANGE_ERASE = efm32series0["flash_erase"]
    PAGE_WRITE = efm32series0["flash_write"]

    MSC_LOCK = 0x3c
    MSC = 0x400C0000

class EfmFlashSeries1(EfmFlash):
    RANGE_ERASE = efm32series1["flash_erase"]
    PAGE_WRITE = efm32series1["flash_write"]

    MSC_LOCK = 0x40
    MSC = 0x400E0000

class EfmFlashSeries1GG(EfmFlash):
    RANGE_ERASE = efm32series1gg["flash_erase"]
    PAGE_WRITE = efm32series1gg["flash_write"]

    MSC_LOCK = 0x40
    MSC = 0x40000000

class Part:
    def __init__(self, name, flash_class, flash_page_size = None):
        self.name = name
        self.flash_class = flash_class
        self.flash_page_size = flash_page_size

PARTS = {
     16: Part("EFR32MG1P",   EfmFlashSeries1),
     17: Part("EFR32MG1B",   EfmFlashSeries1),
     18: Part("EFR32MG1V",   EfmFlashSeries1),
     19: Part("EFR32BG1P",   EfmFlashSeries1),
     20: Part("EFR32BG1B",   EfmFlashSeries1),
     21: Part("EFR32BG1V",   EfmFlashSeries1),
     25: Part("EFR32FG1P",   EfmFlashSeries1),
     26: Part("EFR32FG1B",   EfmFlashSeries1),
     27: Part("EFR32FG1V",   EfmFlashSeries1),
     28: Part("EFR32MG12P",  EfmFlashSeries1),
     29: Part("EFR32MG12B",  EfmFlashSeries1),
     30: Part("EFR32MG12V",  EfmFlashSeries1),
     31: Part("EFR32BG12P",  EfmFlashSeries1),
     32: Part("EFR32BG12B",  EfmFlashSeries1),
     33: Part("EFR32BG12V",  EfmFlashSeries1),
     37: Part("EFR32FG12P",  EfmFlashSeries1),
     38: Part("EFR32FG12B",  EfmFlashSeries1),
     39: Part("EFR32FG12V",  EfmFlashSeries1),
     40: Part("EFR32MG13P",  EfmFlashSeries1),
     41: Part("EFR32MG13B",  EfmFlashSeries1),
     42: Part("EFR32MG13V",  EfmFlashSeries1),
     43: Part("EFR32BG13P",  EfmFlashSeries1),
     44: Part("EFR32BG13B",  EfmFlashSeries1),
     45: Part("EFR32BG13V",  EfmFlashSeries1),
     46: Part("EFR32ZG13P",  EfmFlashSeries1),
     49: Part("EFR32FG13P",  EfmFlashSeries1),
     50: Part("EFR32FG13B",  EfmFlashSeries1),
     51: Part("EFR32FG13V",  EfmFlashSeries1),
     52: Part("EFR32MG14P",  EfmFlashSeries1),
     53: Part("EFR32MG14B",  EfmFlashSeries1),
     54: Part("EFR32MG14V",  EfmFlashSeries1),
     55: Part("EFR32BG14P",  EfmFlashSeries1),
     56: Part("EFR32BG14B",  EfmFlashSeries1),
     57: Part("EFR32BG14V",  EfmFlashSeries1),
     58: Part("EFR32ZG14P",  EfmFlashSeries1),
     61: Part("EFR32FG14P",  EfmFlashSeries1),
     62: Part("EFR32FG14B",  EfmFlashSeries1),
     63: Part("EFR32FG14V",  EfmFlashSeries1),
     71: Part("EFM32G",      EfmFlashSeries0G),
     72: Part("EFM32GG",     EfmFlashSeries0),
     73: Part("EFM32TG",     EfmFlashSeries0),
     74: Part("EFM32LG",     EfmFlashSeries0,
              flash_page_size = 2048), # errata DI_E101
     75: Part("EFM32WG",     EfmFlashSeries0),
     76: Part("EFM32ZG",     EfmFlashSeries0),
     77: Part("EFM32HG",     EfmFlashSeries0),
     81: Part("EFM32PG1B",   EfmFlashSeries1),
     83: Part("EFM32JG1B",   EfmFlashSeries1),
     85: Part("EFM32PG12B",  EfmFlashSeries1),
     87: Part("EFM32JG12B",  EfmFlashSeries1),
    100: Part("EFM32GG11B",  EfmFlashSeries1GG),
    103: Part("EFM32TG11B",  EfmFlashSeries1GG),
    106: Part("EFM32GG12B",  EfmFlashSeries1GG),
    120: Part("EZR32LG",     EfmFlashSeries0),
    121: Part("EZR32WG",     EfmFlashSeries0),
    122: Part("EZR32HG",     EfmFlashSeries0),
    }

DEFAULT_PART = Part("EFx32xG", None)

@SoC.db.register(PartId(6, 0x73, 0x1),
                 PartId(6, 0x73, 0x81),
                 PartId(6, 0x73, 0x82),      # ezr32lg
                 PartId(6, 0x73, 0x41),      # efm32tg
                 PartId(6, 0x73, 0xc1),
                 PartId(6, 0x73, 0xc9),
                 PartId(6, 0x73, 0x101),
                 PartId(6, 0x73, 0x2c1),
                 PartId(6, 0x73, 0xbc1),     # ef32fg14
                 PartId(6, 0x73, 0x401),
                 PartId(6, 0x73, 0x901))
class Gecko(SoC):
    DI_BASE = 0x0fe081b0
    
    def __init__(self, dp):
        SoC.__init__(self, "Gecko", dp)

        self.device_identify()

        self.logger.info("MCU UID: %016x", self.uid)

    def erase_all(self):
        flash, = self.children_of_class(EfmFlash)
        flash.mass_erase()

    def device_identify(self):
        self.di_data = self.buses[0].mem_read(self.DI_BASE, self.DI_EMUTEMP)
        
        self.uid, = struct.unpack("<Q", self.di_data[self.DI_UNIQUE:self.DI_UNIQUE+8])
        dev_number, family, prod_ref = struct.unpack("<HBB", self.di_data[self.DI_PART:self.DI_PART+4])
        flash_size, ram_size = struct.unpack("<HH", self.di_data[self.DI_MSIZE:self.DI_MSIZE+4])
        tempgrade, pkgtype, pincount, flash_page_size = \
            struct.unpack("<BBBB", self.di_data[self.DI_MEMINFO:self.DI_MEMINFO+4])
        pkgtype = chr(pkgtype)

        self.logger.info("Family: %d", family)
        self.info = PARTS.get(family, DEFAULT_PART)

        flash_page_size = 2 ** ((flash_page_size + 10) & 0xff)
        if self.info.flash_page_size is not None \
           and flash_page_size != self.info.flash_page_size:
            self.logger.info("Part advertises wrong flash page size %d", flash_page_size)
            flash_page_size = self.info.flash_page_size

        self.flash_size = flash_size * 1024

        name = self.info.name \
               + str(dev_number) + "F" + str(flash_size)
        if pincount:
            name += pkgtype + str(pincount)

        self.name = name


        if name.startswith("EFR"):
            self.mac = self.di_data[self.DI_EUI48+5:self.DI_EUI48-1:-1]
            self.logger.info("EUI48 HWADDR: %s", ':'.join(["%02x"%x for x in self.mac]))

        if pincount:
            self.logger.info("Package: %s%d", self.PACKAGE_NAMES.get(pkgtype, pkgtype), pincount)

        if self.info.flash_class:
            self.child_add(self.info.flash_class("code", 0, flash_size * 1024, flash_page_size, self))
        self.child_add(BusRam("ram", 0x20000000, ram_size * 1024, self.buses[0]))

    PACKAGE_NAMES = {
        'J': "WLCSP",
        'L': "BGA",
        'M': "QFN",
        'Q': "QFP",
        }

    DI_EUI48            = 0x028
    DI_CUSTOMINFO       = 0x030
    DI_MEMINFO          = 0x034
    DI_UNIQUE           = 0x040
    DI_MSIZE            = 0x048
    DI_PART             = 0x04C
    DI_DEVINFOREV       = 0x050
    DI_EMUTEMP          = 0x054
