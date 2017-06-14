from ... import model
import struct
from ...part_id import PartId
from ...db import Db, NoMatch

__all__ = ["MemoryMappedComponent"]

class MemoryMappedComponent(model.BusComponent):
    DEVID = 0xfc0
    PID1 = 0xfd0
    PID0 = 0xfe0
    CID = 0xff0

    class_db = Db()
    db = Db()

    def __init__(self, bus, base):
        model.BusComponent.__init__(self, "Memory Component", bus)
        self.base = base & ~0x3ff

        blob = bus.mem_read(self.base | self.DEVID, 16 * 4)
        self.devid, pid0, pid1, self.cid = struct.unpack("<LLLL", blob[::4])
        self.pid = (pid0 << 32) | pid1

        if self.pid & 0x80000:
            self.partid = PartId(jep106_bank = (self.pid >> 32) & 0xf,
                                 jep106_id = (self.pid >> 12) & 0x7f,
                                 part_no = self.pid & 0xfff,
                                 revision = (self.pid >> 20) & 0xf)
        else:
            jbank, jid = {
                0x41: (4, 0x77),
            }.get((self.pid >> 12) & 0xff, (0xf, (self.pid >> 12) & 0xff))
            self.partid = PartId(jep106_bank = jbank,
                                 jep106_id = jid,
                                 part_no = self.pid & 0xfff,
                                 revision = (self.pid >> 20) & 0xf)

        self.component_class = (self.cid >> 12) & 0xf
        self.dev_type = self.devid >> 24
        
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

    def reg_read(self, offset):
        return self.bus.u32_read(self.base + offset)

    def reg_write(self, offset, value):
        self.bus.u32_write(self.base + offset, value)

    def cmd_reg_read(self, offset):
        return self.bus.cmd_u32_read(self.base + offset)

    def cmd_reg_write(self, offset, data):
        return self.bus.cmd_u32_write(self.base + offset, data)

    def cast(self):
        try:
            return self.class_db.call(self.component_class, self.bus, self.base)
        except NoMatch:
            pass

        if self.component_class == 0x09:
            return CoresightComponent.db.call(self.dev_type, self.bus, self.base)

        if self.component_class == 0x0e:
            try:
                return self.db.call(self.partid, self.bus, self.base)
            except NoMatch:
                pass

        return self

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

class CoresightComponent(MemoryMappedComponent):
    IMCR = 0xf00
    CTS = 0xfa0
    CTC = 0xfa4
    LOCKS = 0xfb4
    LOCK = 0xfb0
    AUTHS = 0xfb8

    db = Db()

    def __init__(self, bus, base):
        MemoryMappedComponent.__init__(self, bus, base)

CoresightComponent.db.register_default(CoresightComponent)
