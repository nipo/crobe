from ....part_id import PartId
from .soc import SoC, StubFlash, BusRam
from ....component.nxp.mdm_ap import MdmAp
from ....db import NoMatch
from ....component.model import Cpu
from ....util.pretty import base2
import binascii
import math
import struct
from .puppet_code import mkl
import time

class CodeFlash(StubFlash):
    RANGE_ERASE = mkl["flash_erase"]
    PAGE_WRITE = mkl["flash_write"]

class MKL0x(SoC):
    SIM_SDID  = 0x40048024
    SIM_FCFG1 = 0x4004804c
    SIM_FCFG2 = 0x40048050
    SIM_UIDH  = 0x40048054
    SIM_UIDMH = 0x40048058
    SIM_UIDML = 0x4004805c
    SIM_UIDL  = 0x40048060

    PINS = [("FG",16), ("FK",24), ("FM", 32), ("xx", 36),
            ("LF", 48), ("xx", 64), ("LK", 80), ("LH", 64),
            ("xx", 100), ("xx", 121), ("LL", 100), ("AF", 20),
            ("MI", 196), ("xx", None), ("xx", 256), ("xx", None)]

    def __init__(self, dp):
        SoC.__init__(self, "MKL0x", dp)

        self.mdm_ap, = dp.children_of_class(MdmAp)

        st = self.mdm_ap.status
        self.logger.info("MDM-AP control: %08x", self.mdm_ap.control)
        self.logger.info("MDM-AP status: %08x", st)

        if not (st & self.mdm_ap.STATUS_SYSTEM_SECURITY):
            self.info_update()

    def info_update(self):
        self.bus = self.buses[0]
        sdid = self.bus.u32_read(self.SIM_SDID)
        fcfg1 = self.bus.u32_read(self.SIM_FCFG1)
        fcfg2 = self.bus.u32_read(self.SIM_FCFG2)
        uidmh = self.bus.u32_read(self.SIM_UIDMH)
        uidml = self.bus.u32_read(self.SIM_UIDML)
        uidl = self.bus.u32_read(self.SIM_UIDL)

        family = sdid >> 28
        subfamily = (sdid >> 24) & 0xf
        series = "KLxMxWVxxxxxxxxx"[(sdid >> 20) & 0xf]
        sramsize = (sdid >> 16) & 0xf
        revid = (sdid >> 12) & 0xf
        dieid = (sdid >> 7) & 0x1f
        pinid = sdid & 0xf

        self.package, self.pins = self.PINS[pinid]
        if self.pins:
            self.logger.info("Package has %d pins", self.pins)
        
        size_id = (fcfg1 >> 24) & 0xf
        if size_id == 0:
            self.flash_size = 8 * 1024
        elif size_id == 0xf:
            self.flash_size = 1024 * 512
        else:
            self.flash_size = 1024 * (16 << (size_id >> 1))
        self.ram_size = 512 << sramsize
        self.uid = ((uidmh & 0xffff) << 64) | (uidml << 32) | uidl

        self.logger.info("MCU UID: %020x", self.uid)

        self.logger.info("Flash: %s, RAM: %s", base2(self.flash_size, "B"), base2(self.ram_size, "B"))

        self.child_add(BusRam("ram", 0x20000000, self.ram_size * 3 // 4, self.bus))
        self.child_add(BusRam("sraml", 0x20000000 - self.ram_size // 4, self.ram_size // 4, self.bus))
        self.child_add(CodeFlash("code", 0, self.flash_size, 1024, self))

        cpu_code = "x"
        cpu, = self.children_of_class(Cpu)
        if cpu.scs.has_fpu:
            cpu_code = "F" # CM7 or CM4
        elif cpu.scs.name.startswith("CM4"):
            cpu_code = "D"
        elif cpu.scs.name.startswith("CM0"):
            cpu_code = "Z"
        self.name = "MK%s%d%d%s%dV%s" % (series, family, subfamily, cpu_code,
                                         self.flash_size // 1024, self.package)
        self.logger.info("Kinetis %s rev. %d", self.name, revid)
        self.logger.info("DIE id %d", dieid)

    def erase_all(self):
        st = self.mdm_ap.status

        self.mdm_ap.erase_all()
        self.force_blank()

        if not (st & self.mdm_ap.STATUS_SYSTEM_SECURITY):
            return

        self.bus.port.port.reset = True
        self.mdm_ap.connect(True)
        self.bus.port.port.line_reset()
        self.bus.port.port.reset = False
        self.bus.port.debug_enable(True)
        self.bus.enable()
#        self.mdm_ap.connect(False)
        cpu, = self.children_of_class(Cpu)
        cpu.scs.enable()
        cpu.fpb.enable()
        cpu.reset()

#    def reset(self):
#        self.mdm_ap.port.port.reset = True
#        self.bus.enable(False)
#        self.mdm_ap.connect(False)
#        time.sleep(.1)
#        self.mdm_ap.port.debug_enable(False)
#        self.mdm_ap.port.port.reset = False

@SoC.db.register(PartId(0, 0xe, 0), PartId(4, 0x3b, 0xbc11))
def kinetis_ducktyping(dp):
    try:
        ap, = dp.children_find(lambda x: isinstance(x, MdmAp))
    except TypeError:
        raise NoMatch("Not a Kinetis")
    return MKL0x(dp)
