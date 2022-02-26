from ....part_id import PartId
from ....component.arm.coresight.scs import Scs
from ....component.arm.dp import DpAccessFailure
from ....component.st.stm32 import Info
from ....component.arm.cortex import Cortex
from .soc import SoC, StubFlash, BusRam
import struct
from .puppet_code import stm32f01
from ... import pin_control
import binascii

class Stm32f1Flash(StubFlash):
    RANGE_ERASE = stm32f01["flash_erase"]
    PAGE_WRITE = stm32f01["flash_write"]

class Stm32f1Opt(StubFlash):
    RANGE_ERASE = stm32f01["opt_erase"]
    PAGE_WRITE = stm32f01["opt_write"]

class Stm32f0PinCtrl(pin_control.Controller):
    MODE   = 0x000
    OTYPE  = 0x004
    OSPEED = 0x008
    PUPD   = 0x00c
    ID     = 0x010
    OD     = 0x014
    BSR    = 0x018
    LCK    = 0x01c
    AFL    = 0x020
    AFH    = 0x024
    BR     = 0x028

    BANK_STRIDE = 0x400

    def __init__(self, bus, base_addr, bank_map):
        self.bus = bus
        self.base_addr = base_addr
        self.bank_map = bank_map
        self.pin_map = {}
        for bank, mask in enumerate(bank_map):
            if not mask:
                continue

            for pin in range(16):
                if not (mask & (1 << pin)):
                    continue

                self.pin_map["%s%d" % (chr(ord('A') + bank), pin)] = bank, pin
            
    def reg(self, bank, off):
        return self.base_addr + self.BANK_STRIDE * bank + off

    @property
    def pin_names(self):
        return list(self.pin_map.keys())

    def pin_get(self, name):
        bank, pin = self.pin_map[name]
        inp = self.bus.u32_read(self.reg(bank, self.ID))
        return (inp >> pin) & 1

    def pin_set(self, name, value):
        bank, pin = self.pin_map[name]
        word = 0x1 if value else 0x10000
        word <<= pin
        ops = [self.bus.cmd_u32_write(self.reg(bank, self.BSR), word)]
        #print(ops)
        self.bus.execute(ops)

    def pin_config(self, name, mode = pin_control.Mode.Input):
        bank, pin = self.pin_map[name]

        rb = [
            self.bus.cmd_u32_read(self.reg(bank, self.MODE)),
            self.bus.cmd_u32_read(self.reg(bank, self.OTYPE)),
            self.bus.cmd_u32_read(self.reg(bank, self.PUPD)),
            ]
        self.bus.execute(rb)
        #print([(x, hex(x.data)) for x in rb])
        m, o, p = [x.data for x in rb]

        pin2 = pin * 2

        m &= ~(3 << pin2)
        o &= ~(1 << pin)
        p &= ~(3 << pin2)

        if mode == pin_control.Mode.Disabled or mode == pin_control.Mode.Input:
            pass
        elif mode == pin_control.Mode.Pushpull:
            m |= 1 << pin2
        elif mode == pin_control.Mode.InputPullup:
            p |= 1 << pin2
        elif mode == pin_control.Mode.InputPulldown:
            p |= 2 << pin2
        elif mode == pin_control.Mode.Opendrain:
            m |= 1 << pin2
            o |= 1 << pin
        elif mode == pin_control.Mode.OpendrainPullup:
            m |= 1 << pin2
            o |= 1 << pin
            p |= 1 << pin2
        else:
            raise NotSupportedError(mode)

        ops = [
            self.bus.cmd_u32_write(self.reg(bank, self.MODE), m),
            self.bus.cmd_u32_write(self.reg(bank, self.OTYPE), o),
            self.bus.cmd_u32_write(self.reg(bank, self.PUPD), p),
            ]
        #print(ops)
        self.bus.execute(ops)

@SoC.db.register(*[PartId(0, 0x20, did) for did in Info.parts.keys() if did])
class Stm(SoC, pin_control.Controller):
    def __init__(self, dp):
        SoC.__init__(self, "STM32", dp)

        self.info = Info.from_soc(self)
        self.name = self.info.name

    def start(self):
        super().start()

        try:
            uid_blob = self.info.uid_read(self)
            self.uid = int.from_bytes(uid_blob, byteorder = "little")
            self.logger.note("MCU UID: %024x", self.uid)
        except:
            self.logger.warning("Unable to read UID")

        try:
            ram_size = self.ram_size_probe(0x20000000, 512 * 1024)
            self.info.flash_add(lambda name, base, size, page: self.child_add(Stm32f1Flash(name, base, size, page, self)),
                                self.info.flash_kb_get(self))
            self.child_add(Stm32f1Opt("opt", 0x1ffff800, 16, 16, self))
            self.child_add(BusRam("ram", 0x20000000, ram_size, self.buses[0]))
        except:
            self.logger.warning("Unable to get RAM size")

        if self.info.uid_blob_is_coords:
            x, y, no, self.lot_number = struct.unpack("<HHB7s", uid_blob)
            self.wafer_pos = no, x, y
            self.logger.note("Wafer no %d, position %d,%d", *self.wafer_pos)
            self.logger.note("Lot number: %s", self.lot_number)

        if self.info.gpio:
            base, banks = self.info.gpio
            self.gpio = Stm32f0PinCtrl(self.bus, base, banks)

    def attach(self):
        if self.attached:
            return

        self._attach()

    def _attach(self):
        SoC.attach(self)
        cpu, = self.children_of_class(Cortex)
        cpu.reset()
        if self.info.dbgmcu_addr:
            ops = []
            for a, v in sorted(self.info.dbgmcu_init.items()):
                ops.append(self.bus.cmd_u32_write(self.info.dbgmcu_addr + a, v))
            ops += [
                self.bus.cmd_u32_write(0x40021014, 0xffffffff),
                self.bus.cmd_u32_write(0x40021018, 0xffffffff),
                self.bus.cmd_u32_write(0x4002101c, 0xffffffff),
                ]
            if ops:
                self.bus.execute(ops)

    def detach(self):
        if not self.attached:
            return

        if self.info.dbgmcu_addr:
            ops = []
            for a in sorted(self.info.dbgmcu_init.keys()):
                ops.append(self.bus.cmd_u32_write(self.info.dbgmcu_addr + a, 0))
            ops += [
                self.bus.cmd_u32_write(0x40021014, 0),
                self.bus.cmd_u32_write(0x40021018, 0),
                self.bus.cmd_u32_write(0x4002101c, 0),
                ]
            if ops:
                self.bus.execute(ops)
        SoC.detach(self)

    def run_attached(self):
        self.bus.execute([
            self.bus.cmd_u32_write(0x40021014, 0),
            self.bus.cmd_u32_write(0x40021018, 0),
            self.bus.cmd_u32_write(0x4002101c, 0),
            ])
        SoC.run_attached(self)

    def erase_all(self):
        self.attach()
        f = self.info.flash_class(self.bus)
        f.mass_erase()
        f.opt_erase()

        self.reset()
        self.reattach()
        
    def reset(self):
        self.attach()
        f = self.info.flash_class(self.bus)
        try:
            f.reload()
        except DpAccessFailure:
            pass

    @property
    def pin_names(self):
        return self.gpio.pin_names

    def pin_get(self, name):
        return self.gpio.pin_get(name)

    def pin_get_many(self, names = None):
        return self.gpio.pin_get_many(names)

    def pin_set(self, name, value):
        self.gpio.pin_set(name, value)

    def pin_config(self, name, mode = pin_control.Mode.Input):
        self.gpio.pin_config(name, mode)

    def program_end(self, success, do_start):
        f = self.info.flash_class(self.bus)

        if hasattr(f, "reload"):
            SoC.program_end(self, success, False)
            if do_start:
                if not success:
                    return
                f.opt_unlock()
                f.reload()
        else:
            SoC.program_end(self, success, do_start)

