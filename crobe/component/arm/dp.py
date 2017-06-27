from ...model import Component, PortComponent
import time

__all__ = ["Dp", "Run", "ApRead", "ApWrite", "DpAccessFailure"]

class DpAccessFailure(Exception):
    pass

class Dp(PortComponent):
    CTRLSTAT = 0x1 # RW (DPBank = 0)
    DLCR     = 0x5 # RW (DPBank = 1)
    TARGETID = 0x9 # RW (DPBank = 2)
    DLPIDR   = 0xd # RW (DPBank = 3)
    SELECT   = 2 # W
    RDBUFF   = 3 # R
    
    def __init__(self, name, port):
        PortComponent.__init__(self, name, port)

        self.last_ap = None
        self.last_ap_bank = None
        self.last_dp_bank = None

    def start(self):
        from ...part_id import PartId

        self.debug_enable(True)

        from .ap import Ap

        for i in range(16):
            ap = Ap(self, i)

            self.abort()

            if ap.idr == 0:
                continue
            
            self.child_add(ap.cast())

        PortComponent.start(self)

    def debug_enable(self, enabled):
        if not enabled:
            self.ctrlstat = 0
        else:
            self.abort(0x1f)
            self.ctrlstat = 0x50000020
            count = 0
            while self.ctrlstat & 0xa0000000 != 0xa0000000:
                self.ctrlstat = 0x50000020
                time.sleep(.005)
                if count > 3:
                    raise RuntimeError("Unable to enable debugger on DP, CTRL/STAT = 0x%08x" % self.ctrlstat)
                count += 1
            self.ctrlstat = 0x50000021

    def cmd_ap_read(self, ap, addr):
        return ApRead(ap, addr)

    def cmd_ap_write(self, ap, addr, data):
        return ApWrite(ap, addr, data)

    def cmd_run(self, cycles = 1):
        return Run(cycles)

    @property
    def idcode(self):
        raise NotImplementedError()

    @property
    def ctrlstat(self):
        raise NotImplementedError()

    @ctrlstat.setter
    def ctrlstat(self, data):
        raise NotImplementedError()

    def abort(self, what = 0x1f):
        raise NotImplementedError()

class Run:
    def __init__(self, cycles = 1):
        self.cycles = cycles

class ApRead:
    def __init__(self, ap, addr):
        self.ap = ap
        self.addr = addr

class ApWrite:
    def __init__(self, ap, addr, data):
        self.ap = ap
        self.addr = addr
        self.data = data
