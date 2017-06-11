from ..adapter import swd, jtag
from ..model import Component
import time

__all__ = ["Dap", "Idcode", "Abort", "CtrlStat", "RdBuff", "ApRead", "ApWrite"]

class Dap(Component):
    SWDAP = object()
    JTAGDAP = object()

    IDCODE = 0 # R
    ABORT = 0 # W
    CTRLSTAT = 0x1 # RW (DPBank = 0)
    DCLR     = 0x5 # RW (DPBank = 1)
    TARGETID = 0x9 # RW (DPBank = 2)
    DLPIDR   = 0xd # RW (DPBank = 3)
    RESEND = 2 # R
    SELECT = 2 # W
    RDBUFF = 3 # R
    
    def __init__(self, interface):
        self.interface = interface
        if isinstance(self.interface, swd.Interface):
            self.mode = self.SWDAP
            name = "SW-DP"
        elif isinstance(self.interface, jtag.Interface):
            self.mode = self.JTAGDAP
            name = "JTAG-DP"
        else:
            raise ValueError("Unknown interface type")

        Component.__init__(self, name)

        self.last_ap = None
        self.last_ap_bank = None
        self.last_dp_bank = None

    def run(self, operations):
        ops = []
        for o in operations:
            if isinstance(o, (swd.Operation, jtag.Operation)):
                ops.append(o)
            elif isinstance(o, Operation):
                o.__ops = list(o.operations(self))
                ops += o.__ops

        before = -len(ops)
        for o in operations:
            for i in range(len(o.__ops)):
                if before + i < -1 \
                       and isinstance(ops[before + i], swd.Read) \
                       and not ops[before + i].ap \
                       and ops[before + i].addr == 3 \
                       and isinstance(ops[before + i + 1], swd.Read) \
                       and ops[before + i + 1].ap:
                    del ops[before + i]
                    o.__ops[i] = ops[before + i + 1]
            before += len(o.__ops)

        self.interface.run(ops)

        for o in operations:
            if isinstance(o, (swd.Operation, jtag.Operation)):
                pass
            elif isinstance(o, Operation):
                o.update(o.__ops)

    @property
    def idcode(self):
        ops = [Idcode()]
        self.run(ops)
        return ops[0].data

    @property
    def ctrlstat(self):
        ops = [CtrlStat()]
        self.run(ops)
        return ops[0].data

    @ctrlstat.setter
    def ctrlstat(self, data):
        ops = [CtrlStat(data)]
        self.run(ops)

    def abort(self, what = 0x1f):
        ops = [Abort(what)]
        self.run(ops)

    def debug_enable(self, enabled):
        if not enabled:
            self.ctrlstat = 0
        else:
            if self.mode == self.SWDAP:
                self.interface.run([swd.Wakeup(), swd.JtagToSwd(), swd.Read(False, Dap.IDCODE)])

            count = 0
            while self.ctrlstat & 0xa0000000 != 0xa0000000:
                self.ctrlstat = 0x50000000
                time.sleep(.005)
                if count > 3:
                    raise RuntimeError("Unable to enable debugger on DP, CTRL/STAT = 0x%08x" % self.ctrlstat)
                count += 1

    def discover(self):
        from .ap import Ap

        for i in range(16):
            ap = Ap(self, i)

            self.abort()

            if ap.idr == 0:
                continue

            self.children.append(ap.cast())

    def component(self):
        from ..target.soc.arm_based.soc import SoC
        from .component.rom_table import RomTable

        self.debug_enable(True)
        self.discover()

        rts = self.children_find(lambda x: isinstance(x, RomTable))
        part_id = rts[0].partid

        if rts:
            return SoC.db.get(part_id)(self)

        return SoC.db.get(None)(self)

class Operation:
    def __init__(self):
        pass

    def __repr__(self):
        return "dap.%s()" % (self.__class__.__name__)

    def update(self, ops):
        pass

class Idcode(Operation):
    def operations(self, dap):
        if dap.mode == dap.SWDAP:
            return [swd.Read(False, Dap.IDCODE)]

    def update(self, ops):
        self.data = ops[0].data

class Abort(Operation):
    def __init__(self, what = 0x1f):
        self.what = what

    def operations(self, dap):
        if dap.mode == dap.SWDAP:
            return [swd.Write(False, Dap.ABORT, self.what)]

    def __repr__(self):
        return "dap.Abort(0x%x)" % (self.what)

class DpBankedOperation(Operation):
    def __init__(self, address, data = None):
        self.address = address
        self.data = data
        if data is None:
            self.mode = "read"
        else:
            self.mode = "write"

    def operations(self, dap):
        if dap.mode == dap.SWDAP:
            ret = Select(dp_bank = self.address >> 2).operations(dap)
        else:
            assert (self.address >> 2) == 0
            ret = []

        if dap.mode == dap.SWDAP:
            if self.mode == "read":
                return ret + [swd.Read(False, self.address & 3)]
            else:
                return ret + [swd.Write(False, self.address & 3, self.data)]

    def update(self, ops):
        if self.mode == "read":
            self.data = ops[-1].data

    def __repr__(self):
        if self.mode == "read":
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class CtrlStat(DpBankedOperation):
    def __init__(self, data = None):
        DpBankedOperation.__init__(self, Dap.CTRLSTAT, data)
        
    def __repr__(self):
        if self.mode == "read":
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class Select(Operation):
    def __init__(self, ap = None, ap_bank = None, dp_bank = None):
        self.ap = ap
        self.ap_bank = ap_bank
        self.dp_bank = dp_bank

    def operations(self, dap):
        if dap.mode == dap.SWDAP:
            sel = (dap.last_ap, dap.last_ap_bank, dap.last_dp_bank)
            if self.ap is not None or dap.last_ap is None:
                dap.last_ap = self.ap or 0
            if self.ap_bank is not None or dap.last_ap_bank is None:
                dap.last_ap_bank = self.ap_bank or 0
            if self.dp_bank is not None or dap.last_dp_bank is None:
                dap.last_dp_bank = self.dp_bank or 0
            nsel = (dap.last_ap, dap.last_ap_bank, dap.last_dp_bank)
            if sel == nsel:
                return []
            data = (nsel[0] << 24) | (nsel[1] << 4) | (nsel[2])
            return [swd.Write(False, Dap.SELECT, data)]

    def __repr__(self):
        return "dap.Select(%d, %d, %d)" % (self.ap, self.ap_bank, self.dp_bank)

class RdBuff(Operation):
    def operations(self, dap):
        if dap.mode == dap.SWDAP:
            return [swd.Read(False, Dap.RDBUFF)]

    def update(self, ops):
        self.data = ops[0].data

class ApAccess(Operation):
    def __init__(self, addr, ap = 0, be = 0xf):
        self.ap = ap
        self.addr = addr
        self.be = be

    def operations(self, dap):
        return Select(ap = self.ap, ap_bank = self.addr >> 4).operations(dap)

class ApRead(ApAccess):
    def __init__(self, addr, ap = 0, be = 0xf):
        ApAccess.__init__(self, addr, ap, be)

    def operations(self, dap):
        ret = ApAccess.operations(self, dap)
        
        if dap.mode == dap.SWDAP:
            ret += [swd.Read(True, (self.addr >> 2) & 3)]

        return ret + RdBuff().operations(dap)

    def update(self, ops):
        self.data = ops[-1].data

    def __repr__(self):
        return "dap.ApRead(0x%x, %d, 0x%x)" % (self.addr, self.ap, self.be)

class ApWrite(ApAccess):
    def __init__(self, addr, data, ap = 0, be = 0xf):
        ApAccess.__init__(self, addr, ap, be)
        self.data = data

    def operations(self, dap):
        ret = ApAccess.operations(self, dap)
        
        if dap.mode == dap.SWDAP:
            return ret + [swd.Write(True, (self.addr >> 2) & 3, self.data)]

    def __repr__(self):
        return "dap.ApWrite(0x%x, 0x%x, %d, 0x%x)" % (self.addr, self.data, self.ap, self.be)
