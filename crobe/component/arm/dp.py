from ...model import Component, PortComponent
from ...part_id import PartId
from ...freq_capper import FreqCapper
import time

__all__ = ["Dp", "Run", "ApRead", "ApWrite", "DpAccessFailure"]

class DpAccessFailure(Exception):
    pass

class Dp(PortComponent, FreqCapper):
    CTRLSTAT  = 0x01 # RW (DPBank = 0)
    DLCR      = 0x05 # RW (DPBank = 1)
    TARGETID  = 0x09 # R  (DPBank = 2)
    DLPIDR    = 0x0d # R  (DPBank = 3)
    EVENTSTAT = 0x11 # R  (DPBank = 4)

    DPIDR     = 0 # R
    SELECT    = 2 # W
    RDBUFF    = 3 # R

    def __init__(self, name, port):
        PortComponent.__init__(self, port, name)
        FreqCapper.__init__(self, 100e6)

    def freq_update(self, freq):
        ...
        
    def children_changed(self):
        self.freq_cap_min(self.children)
        self.freq_cap("discovery", None if self.children else 1e6)

    def start(self):
        from ...part_id import PartId

        self.freq_cap("discovery", 1e6)

        idr = self.idr
        self.logger.info("Got IDR: %08x", idr)
        try:
            ver = PartId.from_idcode(idr)
        except ValueError:
            ver = self.idcode
            self.logger.info("Bad IDR, falling back to IDCODE")

        self.idr_or_idcode = ver
        self.minimal = bool(ver.part_no & 0x10)
        self.version = ver.part_no & 0x3

        self.logger.info("DP IDR %s v.%dr%d%s", ver, self.version, ver.revision,
                         ", minimal implementation" if self.minimal else "")

        self.debug_enable(True)

        self.target_id = None

        if self.version >= 2:
            try:
                self.target_id = PartId.from_idcode(self.banked_reg_read(self.TARGETID))
            except Exception:
                pass

            self.logger.info("DP Target ID %s", self.target_id)

        for i in range(16):
            self.__ap_discover(i)
        for i in range(240, 256):
            self.__ap_discover(i)

        PortComponent.start(self)

        self.freq_cap("discovery", None)

    def __ap_discover(self, no):
        from .ap import Ap

        ap = Ap(self, no)
        self.abort(1)

        if ap.idr == 0:
            return

        r = ap.cast()
        self.child_add(r)
        return r

    def child_spawn(self, crit):
        if crit.startswith("ap#"):
            no = int(crit[3:])
            self.logger.info("Spawning AP %d", no)
            return self.__ap_discover(no)
        
    def __str__(self):
        try:
            ret = "%s v.%dr%d" % (self.name, self.version, self.idr_or_idcode.revision)
            if self.minimal:
                ret += ", minimal"
            if self.target_id:
                ret += ", Target ID: %s" % self.target_id.pretty()
            return ret
        except AttributeError:
            return self.name

    def debug_enable(self, enabled):
        if not enabled:
            self.ctrlstat = 0
        else:
            self.ctrlstat = 0x50000020
            count = 0
            while self.ctrlstat & 0xa0000000 != 0xa0000000:
                self.ctrlstat = 0x50000020
                time.sleep(.005)
                if count > 3:
                    raise RuntimeError("Unable to enable debugger on DP, CTRL/STAT = 0x%08x" % self.ctrlstat)
                count += 1
            self.ctrlstat = 0x50000021

    @property
    def ctrlstat(self):
        return self.banked_reg_read(self.CTRLSTAT)

    @ctrlstat.setter
    def ctrlstat(self, data):
        self.banked_reg_write(self.CTRLSTAT, data)

    @property
    def dlcr(self):
        return self.banked_reg_read(self.DLCR)

    @dlcr.setter
    def dlcr(self, data):
        self.banked_reg_write(self.DLCR, data)

    def cmd_ap_read(self, ap, addr, interval = 0):
        return ApRead(ap, addr, interval)

    def cmd_ap_write(self, ap, addr, data, interval = 0):
        return ApWrite(ap, addr, data, interval)

    def cmd_run(self, cycles = 1):
        return Run(cycles)

    def run(self, cycles = 1):
        op = self.port.cmd_run(cycles)
        self.port.execute([op])

    def banked_reg_read(self, regno):
        raise NotImplementedError()

    def banked_reg_write(self, regno, value):
        raise NotImplementedError()

    def abort(self, what = 0x1f):
        raise NotImplementedError()

class Run:
    def __init__(self, cycles = 1):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles

    def __repr__(self):
        return "dp.Run(%d)" % self.cycles

class ApRead:
    def __init__(self, ap, addr, interval = 0):
        self.ap = ap
        self.addr = addr
        self.interval = interval

    def __str__(self):
        return "<AP#%d read 0x%x>" % (self.ap, self.addr)

    def __repr__(self):
        return "dp.ApRead(%d, 0x%x, %s)" % (self.ap, self.addr, self.interval)

class ApWrite:
    def __init__(self, ap, addr, data, interval = 0):
        self.ap = ap
        self.addr = addr
        self.data = data
        self.interval = interval

    def __str__(self):
        return "<AP#%d write 0x%x 0x%08x>" % (self.ap, self.addr, self.data)

    def __repr__(self):
        return "dp.ApWrite(%d, 0x%x, 0x%08x, %s)" % (self.ap, self.addr, self.data, self.interval)
