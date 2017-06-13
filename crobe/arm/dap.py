from ..adapter import swd, jtag
from ..model import Component, PortComponent
from ..part_id import PartId
import time

__all__ = ["Dap", "Idcode", "Abort", "CtrlStat", "RdBuff", "ApRead", "ApWrite"]

@jtag.Chain.db.register(PartId.from_idcode(0x0ba00477))
def jtagdp_irlen():
    return 4

@jtag.Tap.db.register(PartId.from_idcode(0x0ba00477))
class JtagDp(jtag.Tap):
    def __init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post):
        jtag.Tap.__init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post)
        self.name = "JTAG-DP Tap"

        self.children.append(Dap(self))

class Dap(PortComponent):
    SWD_IDCODE   = 0 # R
    SWD_ABORT    = 0 # W
    DP_CTRLSTAT = 0x1 # RW (DPBank = 0)
    DP_DCLR     = 0x5 # RW (DPBank = 1)
    DP_TARGETID = 0x9 # RW (DPBank = 2)
    DP_DLPIDR   = 0xd # RW (DPBank = 3)
    SWD_RESEND   = 2 # R
    DP_SELECT   = 2 # W
    DP_RDBUFF   = 3 # R

    JTAG_IDCODE  = 0xe
    JTAG_DPACC   = 0xa
    JTAG_APACC   = 0xb
    JTAG_ABORT   = 0x8
    
    def __init__(self, port):
        self.port = port

        PortComponent.__init__(self, "DP", port)

        self.last_ap = None
        self.last_ap_bank = None
        self.last_dp_bank = None

        from ..target.soc.arm_based.soc import SoC
        from .component.rom_table import RomTable
        from ..part_id import PartId

        self.debug_enable(True)
        self.discover()

        rts = self.children_find(lambda x: isinstance(x, RomTable))

        if rts:
            part_id = rts[0].partid
        else:
            part_id = PartId(0,0,0,0)
            
        self.children.insert(0, SoC.db.call(part_id, self))

    def execute(self, operations):
        ops = []
        for o in operations:
            if isinstance(o, (swd.Operation, jtag.TapOperation)):
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

        self.port.execute(ops)

        for o in operations:
            if isinstance(o, (swd.Operation, jtag.Operation)):
                pass
            elif isinstance(o, Operation):
                o.update(o.__ops)

    @property
    def idcode(self):
        ops = [Idcode()]
        self.execute(ops)
        return ops[0].data

    @property
    def ctrlstat(self):
        ops = [CtrlStat()]
        self.execute(ops)
        return ops[0].data

    @ctrlstat.setter
    def ctrlstat(self, data):
        ops = [CtrlStat(data)]
        self.execute(ops)

    def abort(self, what = 0x1f):
        ops = [Abort(what)]
        self.execute(ops)

    def debug_enable(self, enabled):
        if not enabled:
            self.ctrlstat = 0
        else:
            if isinstance(self.port, swd.Interface):
                self.port.execute([swd.Wakeup(), swd.JtagToSwd(), swd.Wakeup(),
                                        swd.Run(10), swd.Read(False, Dap.SWD_IDCODE)])
            elif isinstance(self.port, jtag.Tap):
                pass

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

class Operation:
    def __init__(self):
        pass

    def __repr__(self):
        return "dap.%s()" % (self.__class__.__name__)

    def update(self, ops):
        pass

class Idcode(Operation):
    def operations(self, dp):
        if isinstance(dp.port, swd.Interface):
            return [swd.Read(False, Dap.SWD_IDCODE)]
        elif isinstance(dp.port, jtag.Tap):
            return [dp.port.cmd_dr_shift(Dap.JTAG_IDCODE, 0, 32)]

    def update(self, ops):
        if isinstance(ops[-1], jtag.TapOperation):
            self.data = ops[-1].tdo
        else:
            self.data = ops[-1].data

class Abort(Operation):
    def __init__(self, what = 0x1f):
        self.what = what

    def operations(self, dp):
        if isinstance(dp.port, swd.Interface):
            return [swd.Write(False, Dap.SWD_ABORT, self.what)]
        elif isinstance(dp.port, jtag.Tap):
            return [dp.port.cmd_dr_shift(Dap.JTAG_ABORT, 1, 35)]

    def __repr__(self):
        return "dap.Abort(0x%x)" % (self.what)

class DpBankedOperation(Operation):
    def __init__(self, address, data = None):
        self.address = address
        self.data = data
        self.is_read = data is None

    def operations(self, dp):
        ret = Select(dp_bank = self.address >> 2).operations(dp)
        
        if isinstance(dp.port, swd.Interface):
            if self.is_read:
                return ret + [swd.Read(False, self.address & 3)]
            else:
                return ret + [swd.Write(False, self.address & 3, self.data)]
        elif isinstance(dp.port, jtag.Tap):
            if self.is_read:
                return ret + [dp.port.cmd_dr_shift(Dap.JTAG_DPACC, ((self.address & 3) << 1) | 1, 35),
                              dp.port.cmd_run(40),
                              dp.port.cmd_dr_shift(Dap.JTAG_DPACC, 1, 35)]
            else:
                return ret + [dp.port.cmd_dr_shift(Dap.JTAG_DPACC, (self.data << 3) | ((self.address & 3) << 1), 35)]

    def update(self, ops):
        if self.is_read:
            if isinstance(ops[-1], jtag.TapOperation):
                self.data = ops[-1].tdo >> 3
                assert ops[-1].tdo & 7 == 2, ops[-1].tdo & 7
            else:
                self.data = ops[-1].data

    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class CtrlStat(DpBankedOperation):
    def __init__(self, data = None):
        DpBankedOperation.__init__(self, Dap.DP_CTRLSTAT, data)
        
    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class Select(Operation):
    def __init__(self, ap = None, ap_bank = None, dp_bank = None):
        self.ap = ap
        self.ap_bank = ap_bank
        self.dp_bank = dp_bank

    def operations(self, dp):
        sel = (dp.last_ap, dp.last_ap_bank, dp.last_dp_bank)
        if self.ap is not None or dp.last_ap is None:
            dp.last_ap = self.ap or 0
        if self.ap_bank is not None or dp.last_ap_bank is None:
            dp.last_ap_bank = self.ap_bank or 0
        if self.dp_bank is not None or dp.last_dp_bank is None:
            dp.last_dp_bank = self.dp_bank or 0
        nsel = (dp.last_ap, dp.last_ap_bank, dp.last_dp_bank)
        if sel == nsel:
            return []
        data = (nsel[0] << 24) | (nsel[1] << 4) | (nsel[2])

        if isinstance(dp.port, swd.Interface):
            return [swd.Write(False, Dap.DP_SELECT, data)]
        elif isinstance(dp.port, jtag.Tap):
            return [dp.port.cmd_dr_shift(Dap.JTAG_DPACC, (data << 3) | (Dap.DP_SELECT << 1), 35)]

    def __repr__(self):
        return "dap.Select(%d, %d, %d)" % (self.ap, self.ap_bank, self.dp_bank)

class RdBuff(Operation):
    def operations(self, dp):
        if isinstance(dp.port, swd.Interface):
            return [swd.Read(False, Dap.DP_RDBUFF)]
        elif isinstance(dp.port, jtag.Tap):
            return [dp.port.cmd_dr_shift(Dap.JTAG_DPACC, (Dap.DP_RDBUFF << 1) | 1, 35)]

    def update(self, ops):
        if isinstance(ops[-1], jtag.TapOperation):
            self.data = ops[-1].tdo >> 3
            assert ops[-1].tdo & 7 == 2, ops[-1].tdo & 7
        else:
            self.data = ops[-1].data

class ApAccess(Operation):
    def __init__(self, addr, ap = 0, be = 0xf):
        self.ap = ap
        self.addr = addr
        self.be = be

    def operations(self, dp):
        return Select(ap = self.ap, ap_bank = self.addr >> 4).operations(dp)

class ApRead(ApAccess):
    def __init__(self, addr, ap = 0, be = 0xf):
        ApAccess.__init__(self, addr, ap, be)

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        if isinstance(dp.port, swd.Interface):
            ret.append(swd.Read(True, (self.addr >> 2) & 3))
        elif isinstance(dp.port, jtag.Tap):
            ret.append(dp.port.cmd_dr_shift(Dap.JTAG_APACC, ((self.addr >> 1) & 0x6) | 1, 35))
            ret.append(dp.port.cmd_run(40))

        return ret + RdBuff().operations(dp)

    def update(self, ops):
        if isinstance(ops[-1], jtag.TapOperation):
            self.data = ops[-1].tdo >> 3
            assert ops[-1].tdo & 7 == 2, ops[-1].tdo & 7
        else:
            self.data = ops[-1].data

    def __repr__(self):
        return "dap.ApRead(0x%x, %d, 0x%x)" % (self.addr, self.ap, self.be)

class ApWrite(ApAccess):
    def __init__(self, addr, data, ap = 0, be = 0xf):
        ApAccess.__init__(self, addr, ap, be)
        self.data = data

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        if isinstance(dp.port, swd.Interface):
            return ret + [swd.Write(True, (self.addr >> 2) & 3, self.data)]
        elif isinstance(dp.port, jtag.Tap):
            return ret + [dp.port.cmd_dr_shift(Dap.JTAG_APACC, (self.data << 3) | ((self.addr >> 1) & 0x6), 35),
                          dp.port.cmd_run(40)]

    def __repr__(self):
        return "dap.ApWrite(0x%x, 0x%x, %d, 0x%x)" % (self.addr, self.data, self.ap, self.be)
