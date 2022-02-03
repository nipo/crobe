from .... import model
import struct
from ....part_id import PartId
from ....db import Db, NoMatch

__all__ = ["MemoryMappedComponent"]

class MemoryMappedComponent(model.Bus32Component):
    DEVARCH = 0xfbc
    DEVID = 0xfc0
    PID1 = 0xfd0
    PID0 = 0xfe0
    CID = 0xff0

    class_db = Db("Coresight class")
    db = Db("Coresight part")

    def __init__(self, bus, base, name = None):
        model.Bus32Component.__init__(self, bus, base & ~0x3ff,
                                      name or "Memory Component")

        blob = bus.mem_read(self.base | self.DEVID, 16 * 4)
        self.devid, pid0, pid1, self.cid = struct.unpack("<LLLL", blob[::4])
        devarch = int.from_bytes(bus.mem_read(self.base | self.DEVARCH, 4), "little")
        if devarch & 0x00100000:
            self.devarch = PartId(devarch >> 28, (devarch >> 21) & 0x7f, devarch & 0xffff, (devarch >> 16) & 0xf)
        else:
            self.devarch = None
        self.pid = (pid0 << 32) | pid1

        self.use_jep106 = bool(self.pid & 0x80000)

        self.partid = PartId(jep106_bank = (self.pid >> 32) & 0xf,
                             jep106_id = (self.pid >> 12) & 0x7f,
                             part_no = self.pid & 0xfff,
                             revision = (self.pid >> 20) & 0xf)

        self.logger.info("@0x%08x, ID: %08x %16x %08x (%s) jep106: %s",
                         self.base,
                         self.devid, self.pid, self.cid, self.partid,
                         self.use_jep106)

        self.logger.info("Devarch: %s", self.devarch)

        self.component_class = (self.cid >> 12) & 0xf
        self.dev_type = self.devid >> 24

        if not name:
            self.name = "Unknown"
            if self.component_class == 0x0:
                self.name = "Generic"
            elif self.component_class == 0x1:
                self.name = "ROM Table"
            elif self.component_class == 0x9:
                self.name = "Coresight " + self.class9_names.get(self.dev_type, "Other")
            elif self.component_class == 0xb:
                self.name = "Peripheral test block"
            elif self.component_class == 0xe:
                self.name = "Generic " + self.classe_names.get(self.pid, "Other 0x%08x" % self.pid)
            elif self.component_class == 0xf:
                self.name = "System"

            self.name = "<0x%08x: %s (0x%08x/0x%08x)>" % (self.base, self.name, self.pid, self.cid)

    def cast(self):
        if self.devarch:
            try:
                return self.db.call(self.devarch, self.bus, self.base)
            except NoMatch:
                pass

        if self.use_jep106:
            try:
                return self.db.call(self.partid, self.bus, self.base)
            except NoMatch:
                pass

        try:
            return self.class_db.call(self.component_class, self.bus, self.base)
        except NoMatch:
            pass

        if self.component_class == 0x09:
            try:
                return CoresightComponent.db.call(self.dev_type, self.bus, self.base)
            except NoMatch:
                pass

        self.logger.info("No specific handler for %s class 0x%02x type 0x%02x %s",
                         self.partid,
                         self.component_class, self.dev_type,
                         self.name)

        return self

    def enable(self, enable = True):
        pass

    class9_names = {
        0x00: "Other",
        0x40: "Validation",
        0x11: "TPIU",
        0x21: "ETB",
        0x31: "Trace router",
        0x12: "Trace funnel",
        0x22: "Filter",
        0x32: "Fifo",
        0x13: "ETM",
        0x23: "DSP trace source",
        0x33: "Coproc trace source",
        0x43: "Bus trace source",
        0x63: "Soft trace source",
        0x15: "CPU Debug",
        0x25: "DSP Debug",
        0x35: "Coproc Debug",
        0x45: "Bus Debug",
        0x55: "TCM Debug",
        0x15: "CPU Perf",
        0x25: "DSP Perf",
        0x35: "Coproc Perf",
        0x45: "Bus Perf",
        0x55: "TCM Perf",
    }

    classe_names = {
        0x4002bb000: "SCS",
        0x4003bb000: "SCS",
        0x4000bb000: "SCS",
        0x4000bb008: "SCS",
        0x4000bb00c: "SCS",
        0x4002bb002: "DWT",
        0x4000bb002: "DWT",
        0x4003bb002: "DWT",
        0x4000bb00a: "DWT",
        0x4000bb001: "ITM",
        0x4002bb001: "ITM",
        0x4003bb001: "ITM",
        0x4000bb00e: "FPB",
        0x4002bb003: "FPB",
        0x4000bb00b: "FPB",
    }

class CoresightAccess:
    def __init__(self, component):
        self.component = component
        state = self.component.reg_read(CoresightComponent.LOCKS)
        self.implemented = bool(state & 1)
        self.should_unlock = False

    def __enter__(self):
        if not self.implemented:
            return

        state = self.component.reg_read(CoresightComponent.LOCKS)

        if state & 2 == 0:
            return

        self.component.reg_write(CoresightComponent.LOCK, CoresightComponent.LOCK_KEY)
        self.should_unlock = True

    def __exit__(self, type, value, traceback):
        if not self.implemented or not self.should_unlock:
            return

        self.component.reg_write(CoresightComponent.LOCK, 0)
        self.should_unlock = False

class CoresightComponent(MemoryMappedComponent):
    IMCR = 0xf00
    CTS = 0xfa0
    CTC = 0xfa4
    LOCKS = 0xfb4
    LOCK = 0xfb0
    LOCK_KEY = 0xc5acce55
    AUTHS = 0xfb8

    db = Db("Coresight component")
    
    def __init__(self, bus, base, name = None):
        MemoryMappedComponent.__init__(self, bus, base, name)

    def access(self):
        return CoresightAccess(self)
