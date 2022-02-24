from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
from ....component.nordic.ctrl_ap import CtrlAp
from ....component.model import Cpu
from ... import pin_control
import binascii
import math
import struct
from .puppet_code import nrf51
import time

class CodeFlash(StubFlash):
    RANGE_ERASE = nrf51["flash_erase"]
    PAGE_WRITE = nrf51["flash_write"]

class UicrFlash(StubFlash):
    PAGE_WRITE = nrf51["flash_write"]
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
        
class nRF5(SoC, pin_control.Controller):
    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)
        self.flash_probe()
        self.ram_probe()
        self.id_probe()
        self.part_probe()

        self.gpio_map = {}
        if self.GPIO_COUNT <= 32:
            ios = range(self.GPIO_COUNT)
            if self.GPIO_COUNT == 15:
                ios = [0, 1, 3, 4, 5, 8, 11, 12, 14, 15, 16, 17, 18, 20, 21]
            if self.GPIO_COUNT == 17:
                ios = [0, 1, 4, 5, 6, 9, 10, 12, 14, 15, 16, 18, 20, 21, 25, 28, 30]
            if self.GPIO_COUNT == 18:
                ios = [0, 1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 17, 18, 20, 28, 29, 30]
            for i in ios:
                self.gpio_map["P%02d" % i] = 0, i
        else:
            for i in range(32):
                self.gpio_map["P0.%02d" % i] = 0, i
            for i in range(self.GPIO_COUNT - 32):
                self.gpio_map["P1.%02d" % i] = 1, i


        self.logger.info("MCU UID: %016x", self.uid)
        self.logger.info("BLE Address: %s %s",
                         self.ble_address[0],
                         ":".join(map("%02x".__mod__, self.ble_address[1])))

    PACKAGES = {
        0: ("QF", "QFN48", 31),
        0x1000: ("CD", "QFN48", 31),
        0x1001: ("CE", "QFN48", 31),
        0x1002: ("CF", "QFN48", 31),
        0x1003: ("CF", "QFN48", 31),
        0x1004: ("QF", "QFN48", 31),
        0x2000: ("QF", "QFN48", 32),
        0x2001: ("CI", "WLCSP56", 32),
        0x2001: ("CA", "WLCSP33", 15),
        0x2003: ("QC", "QFN32", 17),
        0x2004: ("QI", "aQFN73", 48),
        0x2007: ("QD", "QFN32", 18),
        }

    CONFIGID_HW = {
        0x1D: (0x51822, "QF", "AAC0", 31),
        0x1E: (0x51422, "QF", "AACA", 31),
        0x20: (0x51822, "CE", "AABA", 31),
        0x24: (0x51422, "QF", "AAC0", 31),
        0x26: (0x51822, "QF", "ABAA", 31),
        0x27: (0x51822, "QF", "ABA0", 31),
        0x2A: (0x51822, "QF", "AAFA0", 31),
        0x2D: (0x51422, "QF", "AADAA", 31),
        0x2E: (0x51422, "QF", "AAE00", 31),
        0x2F: (0x51822, "CE", "AAB0", 31),
        0x31: (0x51422, "CE", "AAA0A", 31),
        0x3C: (0x51822, "QF", "AAG00", 31),
        0x40: (0x51822, "CE", "AACA0", 31),
        0x44: (0x51822, "QF", "AAGC0", 31),
        0x47: (0x51822, "CE", "AADA0", 31),
        0x4C: (0x51822, "QF", "ABB00", 31),
        0x4D: (0x51822, "CE", "AAD00", 31),
        0x50: (0x51422, "CE", "AAB00", 31),
        0x61: (0x51422, "QF", "ABA00", 31),
        0x72: (0x51822, "QF", "AAH00", 31),
        0x73: (0x51422, "QF", "AAF00", 31),
        0x79: (0x51822, "CE", "AAE00", 31),
        0x7A: (0x51422, "CE", "AAC00", 31),
        0x7B: (0x51822, "QF", "ABC00", 31),
        0x7C: (0x51422, "QF", "ABB00", 31),
        0x7D: (0x51822, "CD", "ABA00", 31),
        0x7E: (0x51422, "CD", "ABA00", 31),
        0x83: (0x51822, "QF", "ACA00", 31),
        0x85: (0x51422, "QF", "ACA00", 31),
        0x86: (0x51422, "QF", "ACA10", 31),
        0x87: (0x51822, "CF", "ACA00", 31),
        0x88: (0x51422, "CF", "ACA00", 31),
        0xeb: (0x52840, "QI", "AAA00", 48),
    }

    def part_probe(self):
        partinfo = self.buses[0].mem_read(self.FICR_PARTINFO, 20)
        configid = self.buses[0].u32_read(self.FICR_CONFIGID)
        package_name = "xx"
        configid_hw = configid & 0xffff

        part, variant, package, ram, flash = struct.unpack("<L4s3L", partinfo)

        if b'\xff\xff\xff\xff' not in partinfo:
            variant = ''.join(chr(x) for x in variant[::-1] if 0x20 < x < 0x7f)
            package_code, package_name, gpio_count \
                          = self.PACKAGES.get(package, ("xx", "Unknown (%04x)" % package, 0))

            if not variant and configid_hw in self.CONFIGID_HW:
                variant = self.CONFIGID_HW[configid_hw][2]
            else:
                v, = struct.unpack("<L", partinfo[4:8])
                self.logger.warning("Cannot get package variant, variant: %08x, configid: %08x",
                                 v, configid)

        elif configid_hw in self.CONFIGID_HW:
            # Fallback on legacy CONFIGID.HW
            part, package_code, variant, gpio_count = self.CONFIGID_HW[configid_hw]

            if package_name == "xx":
                if package_code.startswith("Q"):
                    package_name = "QFN"
                elif package_code.startswith("C"):
                    package_name = "BGA"

        else:
            a, b, c, d, e = struct.unpack("<5L", partinfo)
            self.logger.warning("Cannot get package info, partinfo: %08x/%08x/%08x/%08x/%08x, configid: %08x",
                             a, b, c, d, e, configid)
            return

        self.logger.info("nRF%05x%s%s, %s, %d gpios" % (
            part, package_code, variant, package_name, gpio_count))

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
    NVMC_ERASEUICR = NVMC_BASE + 0x514

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

    GPIO_PIN_CNF = staticmethod(lambda b, p: 0x50000700 + b * 0x300 + p * 4)
    GPIO_PIN_CNF_DIR_OUTPUT       = 0x001
    GPIO_PIN_CNF_INPUT_DISCONNECT = 0x002
    GPIO_PIN_CNF_PULL_DOWN        = 0x004
    GPIO_PIN_CNF_PULL_UP          = 0x00c
    GPIO_PIN_CNF_DRIVE_S0S1       = 0x000
    GPIO_PIN_CNF_DRIVE_H0H1       = 0x300
    GPIO_PIN_CNF_DRIVE_D0S1       = 0x400
    GPIO_PIN_CNF_DRIVE_S0D1       = 0x600
    GPIO_OUT    = staticmethod(lambda b: 0x50000504 + b * 0x300)
    GPIO_OUTSET = staticmethod(lambda b: 0x50000508 + b * 0x300)
    GPIO_OUTCLR = staticmethod(lambda b: 0x5000050c + b * 0x300)
    GPIO_IN     = staticmethod(lambda b: 0x50000510 + b * 0x300)
    GPIO_DIR    = staticmethod(lambda b: 0x50000514 + b * 0x300)
    GPIO_DIRSET = staticmethod(lambda b: 0x50000518 + b * 0x300)
    GPIO_DIRCLR = staticmethod(lambda b: 0x5000051c + b * 0x300)

    def pin_get_many(self, pin_names = None):
        if pin_names is None:
            pin_names = self.pin_names
        pins = dict((name, self.gpio_map[name]) for name in pin_names)
        banks = set(b for (b, p) in pins.values())
        regs = dict((b, self.buses[0].u32_read(self.GPIO_IN(b))) for b in banks)
        ret = {}
        for name, (bank, pin) in pins.items():
            ret[name] = int((regs[bank] >> pin) & 1)
        return ret

    @property
    def pin_names(self):
        return self.gpio_map.keys()

    def pin_get(self, name):
        bank, pin = self.gpio_map[name]
        reg = self.GPIO_IN(bank)
        v = self.buses[0].u32_read(reg)
        self.logger.trace("Getting %s, reg %08x = %08x", name, reg, v)
        return (v >> pin) & 1

    def pin_set(self, name, value):
        bank, pin = self.gpio_map[name]
        reg = self.GPIO_OUTSET(bank) if value else self.GPIO_OUTCLR(bank)
        self.logger.trace("Setting %s to %d, reg %08x", name, int(value), reg)
        self.buses[0].u32_write(reg, 1 << pin)

    def pin_config(self, name, mode):
        bank, pin = self.gpio_map[name]
        reg = self.GPIO_PIN_CNF(bank, pin)
        if not mode & pin_control.Mode.Enabled_:
            value = self.GPIO_PIN_CNF_INPUT_DISCONNECT
        else:
            value = self.GPIO_PIN_CNF_DIR_OUTPUT
            if mode & pin_control.Mode.ResistorUp_:
                value |= self.GPIO_PIN_CNF_PULL_UP
            elif mode & pin_control.Mode.ResistorDown_:
                value |= self.GPIO_PIN_CNF_PULL_DOWN
            if mode & (pin_control.Mode.DriveUp_ | pin_control.Mode.DriveDown_) == (pin_control.Mode.DriveUp_ | pin_control.Mode.DriveDown_):
                value |= self.GPIO_PIN_CNF_DRIVE_S0S1
            elif mode & pin_control.Mode.DriveUp_:
                value |= self.GPIO_PIN_CNF_DRIVE_D0S1
            elif mode & pin_control.Mode.DriveDown_:
                value |= self.GPIO_PIN_CNF_DRIVE_S0D1
            else:
                value &= ~self.GPIO_PIN_CNF_DIR_OUTPUT
            
        self.logger.trace("Setting mode for %s, reg %08x = %08x", name, reg, value)
        self.buses[0].u32_write(reg, value)

class nRF51(nRF5):
    GPIO_COUNT = 31

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
class nRF52832(nRF52):
    GPIO_COUNT = 31

    def __init__(self, dp):
        nRF52.__init__(self, "nRF52832", dp)

@SoC.db.register(PartId(2, 0x44, 8))
class nRF52840(nRF52):
    GPIO_COUNT = 48

    def __init__(self, dp):
        nRF52.__init__(self, "nRF52840", dp)

@SoC.db.register(PartId(2, 0x44, 0xe))
class nRF52820(nRF52):
    GPIO_COUNT = 32

    def __init__(self, dp):
        nRF52.__init__(self, "nRF52811", dp)

@SoC.db.register(PartId(2, 0x44, 0x10))
class nRF52820(nRF52):
    GPIO_COUNT = 18

    def __init__(self, dp):
        nRF52.__init__(self, "nRF52820", dp)
