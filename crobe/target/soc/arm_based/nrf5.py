from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
from ....component.nordic.ctrl_ap import CtrlAp
from ....component.model import Cpu
import binascii
import math
import struct
from .puppet_code import nrf51_flash_erase, nrf51_flash_write
import time

class CodeFlash(StubFlash):
    RANGE_ERASE = nrf51_flash_erase
    PAGE_WRITE = nrf51_flash_write

class UicrFlash(StubFlash):
    PAGE_WRITE = nrf51_flash_write
    UICR_ADDRESS = 0x10001000

    def erase(self, offset, size):
        self.soc.logger.info("Erasing UICR")
        
        self.bus.u32_write(nRF5.NVMC_CONFIG, nRF5.NVMC_CONFIG_EEN)
        while not (self.bus.u32_read(nRF5.NVMC_READY) & nRF5.NVMC_READY_READY):
            pass
        self.bus.u32_write(nRF5.NVMC_ERASEUICR, 1)
        while not (self.bus.u32_read(nRF5.NVMC_READY) & nRF5.NVMC_READY_READY):
            pass
        self.bus.u32_write(nRF5.NVMC_CONFIG, nRF5.NVMC_CONFIG_REN)
        
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

        self.child_add(CodeFlash("code", 0, page_size * code_size, page_size, self))
        self.child_add(UicrFlash("uicr", self.UICR_BASE, page_size, page_size, self))

    def erase_all(self):
        bus = self.buses[0]
        bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_EEN)
        while not (bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        bus.u32_write(self.NVMC_ERASEALL, 1)
        while not (bus.u32_read(self.NVMC_READY) & self.NVMC_READY_READY):
            pass
        bus.u32_write(self.NVMC_CONFIG, self.NVMC_CONFIG_REN)

        self.force_blank()

    NVMC_BASE = 0x4001e000
    NVMC_READY = NVMC_BASE + 0x400
    NVMC_READY_READY = 1
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

    GPIO_PIN_CNF = staticmethod(lambda x: 0x50000700 + x * 4)
    GPIO_PIN_CNF_DIR_OUTPUT       = 0x01
    GPIO_PIN_CNF_INPUT_DISCONNECT = 0x02
    GPIO_PIN_CNF_PULL_DOWN        = 0x04
    GPIO_PIN_CNF_PULL_UP          = 0x0c
    GPIO_PIN_CNF_DRIVE_S0S1       = 0x000
    GPIO_PIN_CNF_DRIVE_H0H1       = 0x300

class nRF51(nRF5):
    def ram_probe(self):
        ram = [self.buses[0].u32_read(self.FICR_RAMINFO + d) for d in range(0, 4*5, 4)]

        assert ram[0] in (1, 2, 3, 4)

        ram_size = sum(ram[1 : 1 + ram[0]])

        self.child_add(BusRam("ram", 0x20000000, ram_size, self.buses[0]))

@SoC.db.register(PartId(2, 0x44, 1))
def nrf51x22(dp):
    return nRF51("nRF51x22", dp)

class nRF52(nRF5):
    def __init__(self, name, dp):
        nRF5.__init__(self, name, dp)

        self.ctrl_ap, = dp.children_of_class(CtrlAp)

    def ram_probe(self):
        ram_kb = self.buses[0].u32_read(self.FICR_PARTINFO + 0xc)

        self.child_add(BusRam("ram", 0x20000000, ram_kb * 1024, self.buses[0]))

    def erase_all(self):
        cpu, = self.children_of_class(Cpu)
        self.ctrl_ap.erase_all()
        self.force_blank()
        cpu.reset()

    def trace_enable(self, width, traceclk_rate, formatted):
        if width not in (None, 1, 2, 4):
            raise ValueError("Unsupported trace width: %s" % width)

        if width is not None:
            self.buses[0].u32_write(self.CLOCK_TRACECONFIG, 1)
            pins = [18]
            div = int(32e6 / traceclk_rate) or 1
        else:
            clk = {16:0, 8:0x10000, 4:0x20000, 2:0x30000}
            mhz = int(traceclk_rate / 1e6 + .5)
            if mhz not in clk:
                raise ValueError("Unsupported trace clock %s" % traceclk_rate)
            cfg = clk[mhz]
            self.buses[0].u32_write(self.CLOCK_TRACECONFIG, cfg | 2)
            pins = [20] + ([18, 16, 15, 24][:width])
            
            div = 1

        for p in pins:
            self.buses[0].u32_write(self.GPIO_PIN_CNF(p), 0
                                    | self.GPIO_PIN_CNF_DIR_OUTPUT
                                    | self.GPIO_PIN_CNF_DRIVE_H0H1
                                    )

        SoC.trace_enable(self, width, div, formatted)

    CLOCK_TRACECONFIG = 0x4000055c
        
@SoC.db.register(PartId(2, 0x44, 6))
def nrf52832(dp):
    return nRF52("nRF52832", dp)

@SoC.db.register(PartId(2, 0x44, 8))
def nrf52840(dp):
    return nRF52("nRF52840", dp)
