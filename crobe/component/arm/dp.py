from ...model import Component, PortComponent
import time

__all__ = ["Dp", "Run", "ApRead", "ApWrite", "DpAccessFailure"]

class DpAccessFailure(Exception):
    pass

class Dp(PortComponent):
    CTRLSTAT  = 0x01 # RW (DPBank = 0)
    DLCR      = 0x05 # RW (DPBank = 1)
    TARGETID  = 0x09 # R  (DPBank = 2)
    DLPIDR    = 0x0d # R  (DPBank = 3)
    EVENTSTAT = 0x11 # R  (DPBank = 4)

    DPIDR     = 0 # R
    SELECT    = 2 # W
    RDBUFF    = 3 # R
    
    def __init__(self, name, port):
        PortComponent.__init__(self, name, port)

    def start(self):
        from ...part_id import PartId

        idr = self.idr
        self.logger.info("Got IDR: %08x", idr)
        try:
            ver = PartId.from_idcode(idr)
        except ValueError:
            ver = self.idcode
            self.logger.info("Bad IDR, falling back to IDCODE")

        self.minimal = bool(ver.part_no & 0x10)
        self.version = ver.part_no & 0x3

        self.logger.info("DP IDR %s v.%dr%d%s", ver, self.version, ver.revision,
                         ", minimal implementation" if self.minimal else "")

        self.debug_enable(True)

        from .ap import Ap

        for i in range(16):
            ap = Ap(self, i)

            self.abort(1)

            if ap.idr == 0:
                continue
            
            self.child_add(ap.cast())

        PortComponent.start(self)

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
