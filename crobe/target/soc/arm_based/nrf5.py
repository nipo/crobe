from ....part_id import PartId
from .soc import SoC
from ....component.nordic.ctrl_ap import CtrlAp
from ....memory.region import *
import binascii
import math
import struct

flash_write_code = binascii.a2b_hex(b'f0b501240b1ca4460b4d0c4f92082c60'+
                                    b'0a4e002a09d064463e682642fbd01c68'+
                                    b'5e1a3450013a0433f2e7012332681a42'+
                                    b'fcd000232b60f0bd04e5014000e40140')

class nRFFlash(NandFlash):
    NVMC_READY       = 0x4001e400
    NVMC_READY_BUSY  = 0
    NVMC_READY_READY = 1
    NVMC_CONFIG      = 0x4001e504
    NVMC_CONFIG_NONE = 0
    NVMC_CONFIG_WEN  = 1
    NVMC_CONFIG_EEN  = 2
    NVMC_ERASEPAGE   = 0x4001e508
    NVMC_ERASEUICR   = 0x4001e514

    def __init__(self, soc, base, size, page_size):
        NandFlash.__init__(self, soc.buses[0], "code", base, size, page_size)
        self.soc = soc
    
    def write_direct(self, program):
        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_WEN)

        for page in program.paged(self.page_size, fill = b'\xff'):
            if not (self.address <= page.address < self.address + self.size):
                continue

            self.soc.logger.info("Writing flash 0x%08x-0x%08x", page.address, page.address + len(page))

            while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
                pass

            self.bus.mem_write(page.address, page.data, 5e-6)

        while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_NONE)

    def write_puppet(self, program):
        puppet = self.soc.puppet()
        code_zone = puppet.allocate(len(flash_write_code))
        page_zone = puppet.allocate(self.page_size), puppet.allocate(self.page_size)
        code_zone.write(flash_write_code)

        running = None
        for i, page in enumerate(program.paged(self.page_size, fill = b'\xff')):
            self.logger.info("Loading page at 0x%08x...", page.address)
            z = page_zone[i % 2]

            chunk = 256
            for i in range(0, self.page_size, chunk):
                z.write(page.data[i:i+chunk], i)

            if running is not None:
                self.logger.info("Done writing page at 0x%08x...", running)
                puppet.wait()
                running = None

            puppet.prepare(code_zone.address, page.address, z.address, self.page_size)
            puppet.run()
            running = page.address

        if running:
            puppet.wait()
            self.logger.info("Done writing page at 0x%08x...", running)

        puppet.unallocate(code_zone)
        puppet.unallocate(page_zone[0])
        puppet.unallocate(page_zone[1])

    def write(self, program):
        self.write_puppet(program)
        
class CodeFlash(nRFFlash):
    def __init__(self, soc, size, page_size):
        nRFFlash.__init__(self, soc, 0, size, page_size)

    def erase(self, address, size):
        aligned_address = address & ~(self.page_size - 1)
        end = address + size
        aligned_end = ((end | (self.page_size - 1)) + 1) if (end & (self.page_size - 1)) else end

        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_EEN)
        for page in range(aligned_address, aligned_end, self.page_size):
            self.soc.logger.info("Erasing page at 0x%08x", page)
            while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
                pass
            self.bus.u32_write(self.NVMC_ERASEPAGE, page)
        while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_NONE)

class UicrFlash(nRFFlash):
    UICR_ADDRESS = 0x10001000

    def __init__(self, soc, size, page_size):
        nRFFlash.__init__(self, soc, self.UICR_ADDRESS, size, page_size)

    def erase(self, address, size):
        if not (address <= self.UICR_ADDRESS < address + size):
            return

        self.soc.logger.info("Erasing UICR")
        
        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_EEN)
        while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        self.bus.u32_write(self.NVMC_ERASEUICR, 1)
        while not (self.bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        self.bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_NONE)
            
        
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

        self.child_add(CodeFlash(self, page_size * code_size, page_size))
        self.child_add(UicrFlash(self, page_size, page_size))

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
