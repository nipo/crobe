from ....part_id import PartId
from .soc import SoC
from ....component.nordic.ctrl_ap import CtrlAp
from ....memory.region import *
import math

class nRF(SoC):
    
    NVMC_BASE = 0x4001e000
    NVMC_READY = NVMC_BASE + 0x400
    NVMC_CONFIG = NVMC_BASE + 0x504
    NVMC_CONFIG_EEN = 2
    NVMC_CONFIG_WEN = 1
    NVMC_CONFIG_REN = 0
    NVMC_ERASEPAGE = NVMC_BASE + 0x508
    NVMC_ERASEALL = NVMC_BASE + 0x50c

    POWER_RESET = 0x40000544

    UICR_BASE = 0x10001000

    FICR_BASE = 0x10000000
    FICR_CODEPAGESIZE = 0x10000010
    FICR_CODESIZE = 0x10000014
    FICR_RBD = 0x10000018
    FICR_DEVICEADDRTYPE = 0x100000a0
    FICR_PARTINFO = 0x10000100
    FICR_RAMINFO = 0x10000034
    FICR_CONFIGID = 0x1000005c

    PACKAGE = {
        0: "QF",
        0x1000: "CD",
        0x1001: "CE",
        0x1002: "CF",
        0x1003: "CF",
    }

    CONFIGID_HW = {
        0x1D: ("51822", "QF", "AA", "C0", 1),
        0x1E: ("51422", "QF", "AA", "CA", 1),
        0x20: ("51822", "CE", "AA", "BA", 1),
        0x24: ("51422", "QF", "AA", "C0", 1),
        0x26: ("51822", "QF", "AB", "AA", 1),
        0x27: ("51822", "QF", "AB", "A0", 1),
        0x2A: ("51822", "QF", "AA", "FA0", 2),
        0x2D: ("51422", "QF", "AA", "DAA", 2),
        0x2E: ("51422", "QF", "AA", "E00", 2),
        0x2F: ("51822", "CE", "AA", "B0", 1),
        0x31: ("51422", "CE", "AA", "A0A", 1),
        0x3C: ("51822", "QF", "AA", "G00", 2),
        0x40: ("51822", "CE", "AA", "CA0", 2),
        0x44: ("51822", "QF", "AA", "GC0", 2),
        0x47: ("51822", "CE", "AA", "DA0", 2),
        0x4C: ("51822", "QF", "AB", "B00", 2),
        0x4D: ("51822", "CE", "AA", "D00", 2),
        0x50: ("51422", "CE", "AA", "B00", 2),
        0x61: ("51422", "QF", "AB", "A00", 2),
        0x72: ("51822", "QF", "AA", "H00", 3),
        0x73: ("51422", "QF", "AA", "F00", 3),
        0x79: ("51822", "CE", "AA", "E00", 3),
        0x7A: ("51422", "CE", "AA", "C00", 3),
        0x7B: ("51822", "QF", "AB", "C00", 3),
        0x7C: ("51422", "QF", "AB", "B00", 3),
        0x7D: ("51822", "CD", "AB", "A00", 3),
        0x7E: ("51422", "CD", "AB", "A00", 3),
        0x83: ("51822", "QF", "AC", "A00", 3),
        0x85: ("51422", "QF", "AC", "A00", 3),
        0x87: ("51822", "CF", "AC", "A00", 3),
        0x88: ("51422", "CF", "AC", "A00", 3),
        0xeb: ("52840", "QI", "AA", "A00", 0),
    }

    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)
        self.flash_probe()
        self.ram_probe()

    def flash_probe(self):
        page_size = self.buses[0].u32_read(self.FICR_CODEPAGESIZE)
        code_size = self.buses[0].u32_read(self.FICR_CODESIZE)

        self.child_add(NandFlash(self.buses[0], "code", 0, page_size * code_size, page_size))
        self.child_add(NandFlash(self.buses[0], "uicr", 0x10001000, page_size, page_size))

class nRF51(nRF):
    def ram_probe(self):
        ram = [self.buses[0].u32_read(self.FICR_RAMINFO + d) for d in range(0, 4*5, 4)]

        assert ram[0] in (1, 2, 3, 4)

        ram_size = sum(ram[1 : 1 + ram[0]])

        self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_size))

@SoC.db.register(PartId(2, 0x44, 1))
def nrf51x22(dp):
    return nRF51("nRF51x22", dp)

class nRF52(nRF):
    def ram_probe(self):
        ram_kb = self.buses[0].u32_read(self.FICR_PARTINFO + 0xc)

        self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_kb * 1024))
        
@SoC.db.register(PartId(2, 0x44, 6))
def nrf52832(dp):
    return nRF52("nRF52832", dp)

@SoC.db.register(PartId(2, 0x44, 8))
def nrf52840(dp):
    return nRF52("nRF52840", dp)
