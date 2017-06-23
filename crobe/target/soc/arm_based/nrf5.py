from ....part_id import PartId
from .soc import SoC
from ....component.nordic.ctrl_ap import CtrlAp
from ....memory.region import *
import binascii
import math
import struct

class nRF5(SoC):
    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)
        self.flash_probe()
        self.ram_probe()
        self.id_probe()

        self.logger.info("MCU UID: %016x", self.uid)
        self.logger.info("BLE Address: %s %s",
                         self.ble_address[0],
                         ":".join(map("%02x".__mod__, self.ble_address[1])))

    def id_probe(self):
        addr = self.buses[0].mem_read(self.FICR_DEVICEADDRTYPE, 12)
        self.logger.info(binascii.b2a_hex(addr))
        ble_addr = addr[9:3:-1]
        if addr[0] & 1:
            ble_addr = bytes([ble_addr[0] | 0xc0]) + ble_addr[1:]
            self.ble_address = ("Static", ble_addr)
        else:
            self.ble_address = ("Public", ble_addr)

        self.uid, = struct.unpack("<Q", self.buses[0].mem_read(self.FICR_DEVICEID, 8))

    def flash_probe(self):
        page_size = self.buses[0].u32_read(self.FICR_CODEPAGESIZE)
        code_size = self.buses[0].u32_read(self.FICR_CODESIZE)

        self.child_add(NandFlash(self.buses[0], "code", 0, page_size * code_size, page_size))
        self.child_add(NandFlash(self.buses[0], "uicr", 0x10001000, page_size, page_size))

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
    FICR_DEVICEID = 0x10000060
    FICR_PARTINFO = 0x10000100
    FICR_RAMINFO = 0x10000034
    FICR_CONFIGID = 0x1000005c

class nRF51(nRF5):
    def ram_probe(self):
        ram = [self.buses[0].u32_read(self.FICR_RAMINFO + d) for d in range(0, 4*5, 4)]

        assert ram[0] in (1, 2, 3, 4)

        ram_size = sum(ram[1 : 1 + ram[0]])

        self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_size))

@SoC.db.register(PartId(2, 0x44, 1))
def nrf51x22(dp):
    return nRF51("nRF51x22", dp)

class nRF52(nRF5):
    def ram_probe(self):
        ram_kb = self.buses[0].u32_read(self.FICR_PARTINFO + 0xc)

        self.child_add(Ram(self.buses[0], "ram", 0x20000000, ram_kb * 1024))

@SoC.db.register(PartId(2, 0x44, 6))
def nrf52832(dp):
    return nRF52("nRF52832", dp)

@SoC.db.register(PartId(2, 0x44, 8))
def nrf52840(dp):
    return nRF52("nRF52840", dp)
