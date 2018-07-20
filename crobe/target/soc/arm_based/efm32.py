from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
import binascii
import struct
import time
from .puppet_code import efm32, efm32gg11

class EfmFlash(StubFlash):
    RANGE_ERASE = efm32["flash_erase"]
    PAGE_WRITE = efm32["flash_write"]
    CMU = 0x400c8000
    CMU_LOCK = 0x084
    CMU_OSCENCMD = 0x020
    CMU_STATUS = 0x02c

    def prepare(self):
        self.soc.buses[0].u32_write(self.CMU | self.CMU_LOCK, 0x580e)
        self.soc.buses[0].u32_write(self.CMU | self.CMU_OSCENCMD, 0x10)
        while not (self.soc.buses[0].u32_read(self.CMU | self.CMU_STATUS) & 0x20):
            pass
        self.soc.buses[0].u32_write(self.CMU | self.CMU_LOCK, 0)

class Efm1GFlash(EfmFlash):
    RANGE_ERASE = efm32gg11["flash_erase"]
    PAGE_WRITE = efm32gg11["flash_write"]
    CMU = 0x400e4000
    CMU_LOCK = 0x180
    CMU_OSCENCMD = 0x60
    CMU_STATUS = 0x90

    MSC_LOCK = 0x40
    MSC_LOCK_MAGIC = 0x1b71
    MSC_WRITECTRL = 0x8
    MSC_WRITECMD = 0xc
    MSC_WRITECMD_ERASEMAIN0 = 1 << 8
    MSC_WRITECMD_ERASEMAIN1 = 1 << 9
    MSC_WRITECMD_ERASEPAGE = 1 << 1
    MSC_WRITECMD_LADDRIM = 1 << 0
    MSC_STATUS = 0x1c
    MSC_STATUS_BUSY = 0x1
    MSC_MASSLOCK = 0x54
    MSC_MASSLOCK_MAGIC = 0x631a
    MSC_ADDRB = 0x10

    def msc_unlock(self):
        msc = self.soc.info.msc
        self.soc.buses[0].u32_write(msc | self.MSC_LOCK, self.MSC_LOCK_MAGIC)

    def msc_lock(self):
        msc = self.soc.info.msc
        self.soc.buses[0].u32_write(msc | self.MSC_LOCK, 0)

    def msc_mass_unlock(self):
        msc = self.soc.info.msc
        self.soc.buses[0].u32_write(msc | self.MSC_MASSLOCK, self.MSC_MASSLOCK_MAGIC)

    def msc_mass_lock(self):
        msc = self.soc.info.msc
        self.soc.buses[0].u32_write(msc | self.MSC_MASSLOCK, 0)

    def mass_erase(self):
        msc = self.soc.info.msc
        self.msc_unlock()
        self.msc_mass_unlock()
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECTRL, 1)
        while self.soc.buses[0].u32_read(msc | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            time.sleep(.01)
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEMAIN0)
        while self.soc.buses[0].u32_read(msc | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            time.sleep(.01)
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEMAIN1)
        while self.soc.buses[0].u32_read(msc | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            time.sleep(.01)
        self.msc_mass_lock()
        self.msc_lock()
        self.is_blank = True

    def _page_erase(self, page):
        msc = self.soc.info.msc
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECTRL, 1)
        self.soc.buses[0].u32_write(msc | self.MSC_ADDRB, page)
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECMD, self.MSC_WRITECMD_LADDRIM)
        self.soc.buses[0].u32_write(msc | self.MSC_WRITECMD, self.MSC_WRITECMD_ERASEPAGE)
        while self.soc.buses[0].u32_read(msc | self.MSC_STATUS) & self.MSC_STATUS_BUSY:
            pass

    def erase(self, offset, size):
        self.soc.attach()
        self.msc_unlock()
        addr = offset & ~(self.page_size - 1)
        while addr < offset + size:
            self._page_erase(addr)
            addr += self.page_size
        self.msc_lock()

        if size == self.size:
            self.is_blank = True

class Part:
    def __init__(self, name, msc, flash_class):
        self.name = name
        self.msc = msc
        self.flash_class = flash_class

PARTS = {
     71: Part("EFM32G",      0x400C0000, EfmFlash),
     72: Part("EFM32GG",     0x400C0000, Efm1GFlash),
     73: Part("EFM32TG",     0x400C0000, EfmFlash),
     74: Part("EFM32LG",     0x400C0000, EfmFlash),
     75: Part("EFM32WG",     0x400C0000, EfmFlash),
     76: Part("EFM32ZG",     0x400C0000, EfmFlash),
     77: Part("EFM32HG",     0x400C0000, EfmFlash),
    100: Part("EFM32GG11B",  0x40000000, Efm1GFlash),
    120: Part("EZR32WG",     0x400C0000, EfmFlash),
    121: Part("EZR32LG",     0x400C0000, EfmFlash),
    122: Part("EZR32HG",     0x400C0000, EfmFlash),
     81: Part("EFM32PG",     0x400E0000, EfmFlash),
     83: Part("EFM32JG",     0x400E0000, EfmFlash),
     16: Part("EFR32MG1P",   0x400E0000, EfmFlash),
     17: Part("EFR32MG1B",   0x400E0000, EfmFlash),
     18: Part("EFR32MG1V",   0x400E0000, EfmFlash),
     19: Part("EFR32BG1P",   0x400E0000, EfmFlash),
     20: Part("EFR32BG1B",   0x400E0000, EfmFlash),
     21: Part("EFR32BG1V",   0x400E0000, EfmFlash),
     25: Part("EFR32FG1B",   0x400E0000, EfmFlash),
     26: Part("EFR32FG1V",   0x400E0000, EfmFlash),
     27: Part("EFR32FG1x",   0x400E0000, EfmFlash),
     28: Part("EFR32MG12P",  0x400E0000, EfmFlash),
    }

DEFAULT_PART = Part("EFx32xG", 0, None)

@SoC.db.register(PartId(6, 0x73, 0x1),
                 PartId(6, 0x73, 0x81),
                 PartId(6, 0x73, 0x82),
                 PartId(6, 0x73, 0xc1),
                 PartId(6, 0x73, 0xc9),
                 PartId(6, 0x73, 0x101),
                 PartId(6, 0x73, 0x2c1),
                 PartId(6, 0x73, 0x401),
                 PartId(6, 0x73, 0x901))
class Gecko(SoC):
    DI_BASE = 0x0fe081b0
    
    def __init__(self, dp):
        SoC.__init__(self, "Gecko", dp)

        self.device_identify()

        self.logger.info("MCU UID: %016x", self.uid)

    def erase_all(self):
        print("mass erase")
        flash, = self.children_of_class(EfmFlash)
        flash.prepare()
        flash.mass_erase()

    def device_identify(self):
        self.di_data = self.buses[0].mem_read(self.DI_BASE, self.DI_EMUTEMP)
        
        self.uid, = struct.unpack("<Q", self.di_data[self.DI_UNIQUE:self.DI_UNIQUE+8])
        dev_number, family, prod_ref = struct.unpack("<HBB", self.di_data[self.DI_PART:self.DI_PART+4])
        flash_size, ram_size = struct.unpack("<HH", self.di_data[self.DI_MSIZE:self.DI_MSIZE+4])
        tempgrade, pkgtype, pincount, flash_page_size = \
            struct.unpack("<BBBB", self.di_data[self.DI_MEMINFO:self.DI_MEMINFO+4])
        pkgtype = chr(pkgtype)
        flash_page_size = 2 ** ((flash_page_size + 10) & 0xff)

        self.info = PARTS.get(family, DEFAULT_PART)

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
