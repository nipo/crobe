from ...adapter.protocol import swd, jtag
from ...model import Component, PortComponent
from ...part_id import PartId
import time

__all__ = []

class Dap(PortComponent):
    DP_CTRLSTAT = 0x1 # RW (DPBank = 0)
    DP_DCLR     = 0x5 # RW (DPBank = 1)
    DP_TARGETID = 0x9 # RW (DPBank = 2)
    DP_DLPIDR   = 0xd # RW (DPBank = 3)
    DP_SELECT   = 2 # W
    DP_RDBUFF   = 3 # R
    
    def __init__(self, name, port):
        PortComponent.__init__(self, name, port)

        self.last_ap = None
        self.last_ap_bank = None
        self.last_dp_bank = None

    def start(self):
        from .coresight.rom_table import RomTable
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

        self.logger.debug("Done:")
        for i, o in enumerate(operations):
            self.logger.debug("- %d, %s: %s", i, o, o.__ops)

        for i, o in enumerate(operations):
            if isinstance(o, (swd.Operation, jtag.Operation)):
                pass
            elif isinstance(o, Operation):
                try:
                    o.update(o.__ops)
                except WaitError as e:
                    self.logger.error("Failed at operation #%d", i)
                    raise

    @property
    def idcode(self):
        ops = [self.cmd_idcode()]
        self.execute(ops)
        return ops[0].data

    @property
    def ctrlstat(self):
        ops = [self.cmd_ctrl_stat()]
        self.execute(ops)
        return ops[0].data

    @ctrlstat.setter
    def ctrlstat(self, data):
        ops = [self.cmd_ctrl_stat(data)]
        self.execute(ops)

    def abort(self, what = 0x1f):
        ops = [self.cmd_abort(what)]
        self.execute(ops)

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

@swd.Interface.db.register(PartId(4, 0x3b, 0xba01),
                           PartId(4, 0x3b, 0xbb11))
class SwDp(Dap):
    IDCODE   = 0 # R
    ABORT    = 0 # W
    RESEND   = 2 # R
    
    def __init__(self, port):
        Dap.__init__(self, "SW-DP", port)

    def cmd_idcode(self):
        return SwdIdCode()

    def cmd_rdbuff(self):
        return SwdRdBuff()

    def cmd_select(self, ap = None, ap_bank = None, dp_bank = None):
        return SwdSelect(ap, ap_bank, dp_bank)

    def cmd_abort(self, what = 0x1f):
        return SwdAbort(what)

    def cmd_ctrl_stat(self, data = None):
        return SwdCtrlStat(data)

    def cmd_ap_read(self, addr, ap = 0, be = 0xf):
        return SwdApRead(addr, ap, be)

    def cmd_ap_write(self, addr, data, ap = 0, be = 0xf):
        return SwdApWrite(addr, data, ap, be)

class JtagDp(Dap):
    IDCODE  = 0xe
    DPACC   = 0xa
    APACC   = 0xb
    ABORT   = 0x8

    def __init__(self, port):
        Dap.__init__(self, "JTAG-DP", port)

    def cmd_idcode(self):
        return JtagIdCode()

    def cmd_rdbuff(self):
        return JtagRdBuff()

    def cmd_select(self, ap = None, ap_bank = None, dp_bank = None):
        return JtagSelect(ap, ap_bank, dp_bank)

    def cmd_abort(self, what = 0x1f):
        return JtagAbort(what)

    def cmd_ctrl_stat(self, data = None):
        return JtagCtrlStat(data)

    def cmd_ap_read(self, addr, ap = 0, be = 0xf):
        return JtagApRead(addr, ap, be)

    def cmd_ap_write(self, addr, data, ap = 0, be = 0xf):
        return JtagApWrite(addr, data, ap, be)

@jtag.Tap.db.register(PartId(4, 0x3b, 0xba00))
class JtagDpTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "JTAG-DP Tap"

    def start(self):
        self.child_add(JtagDp(self))
        jtag.Tap.start(self)

class WaitError(Exception):
    pass

class Operation:
    def __init__(self):
        pass

    def __repr__(self):
        return "dap.%s()" % (self.__class__.__name__)

    def update(self, ops):
        pass

class SwdIdcode(Operation):
    def operations(self, dp):
        return [swd.Read(False, SwDp.IDCODE)]

    def update(self, ops):
        self.data = ops[-1].data

class JtagIdcode(Operation):
    def operations(self, dp):
        return [dp.port.cmd_dr_shift(JtagDp.IDCODE, 0, 32)]

    def update(self, ops):
        self.data = ops[-1].tdo

class SwdAbort(Operation):
    def __init__(self, what = 0x1f):
        self.what = what

    def operations(self, dp):
        return [swd.Write(False, SwDp.ABORT, self.what)]

    def __repr__(self):
        return "dap.Abort(0x%x)" % (self.what)

class JtagAbort(Operation):
    def __init__(self, what = 0x1f):
        self.what = what

    def operations(self, dp):
        return [dp.port.cmd_dr_shift(JtagDp.ABORT, 1, 35)]

    def __repr__(self):
        return "dap.Abort(0x%x)" % (self.what)

class Select(Operation):
    def __init__(self, ap = None, ap_bank = None, dp_bank = None):
        self.ap = ap
        self.ap_bank = ap_bank
        self.dp_bank = dp_bank

    def data(self, dp):
        sel = (dp.last_ap, dp.last_ap_bank, dp.last_dp_bank)
        if self.ap is not None or dp.last_ap is None:
            dp.last_ap = self.ap or 0
        if self.ap_bank is not None or dp.last_ap_bank is None:
            dp.last_ap_bank = self.ap_bank or 0
        if self.dp_bank is not None or dp.last_dp_bank is None:
            dp.last_dp_bank = self.dp_bank or 0
        nsel = (dp.last_ap, dp.last_ap_bank, dp.last_dp_bank)
        if sel == nsel:
            return None
        return (nsel[0] << 24) | (nsel[1] << 4) | (nsel[2])

    def __repr__(self):
        return "dap.Select(%d, %d, %d)" % (self.ap, self.ap_bank, self.dp_bank)

class SwdSelect(Select):
    def operations(self, dp):
        data = self.data(dp)
        if data is None:
            return []
        return [swd.Write(False, Dap.DP_SELECT, data)]

class JtagSelect(Select):
    def operations(self, dp):
        data = self.data(dp)
        if data is None:
            return []
        return [dp.port.cmd_dr_shift(JtagDp.DPACC, (data << 3) | (Dap.DP_SELECT << 1), 35)]

class DpBankedOperation(Operation):
    def __init__(self, address, data = None):
        self.address = address
        self.data = data
        self.is_read = data is None

    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class JtagDpBankedOperation(DpBankedOperation):
    def operations(self, dp):
        ret = dp.cmd_select(dp_bank = self.address >> 2).operations(dp)
        
        if self.is_read:
            return ret + [dp.port.cmd_dr_shift(JtagDp.DPACC, ((self.address & 3) << 1) | 1, 35),
                          dp.port.cmd_run(40),
                          dp.port.cmd_dr_shift(JtagDp.DPACC, 1, 35)]
        else:
            return ret + [dp.port.cmd_dr_shift(JtagDp.DPACC, (self.data << 3) | ((self.address & 3) << 1), 35)]

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        if self.is_read:
            self.data = ops[-1].tdo >> 3

class SwdDpBankedOperation(DpBankedOperation):
    def operations(self, dp):
        ret = dp.cmd_select(dp_bank = self.address >> 2).operations(dp)
        
        if self.is_read:
            return ret + [swd.Read(False, self.address & 3)]
        else:
            return ret + [swd.Write(False, self.address & 3, self.data)]

    def update(self, ops):
        if self.is_read:
            self.data = ops[-1].data

class JtagCtrlStat(JtagDpBankedOperation):
    def __init__(self, data = None):
        JtagDpBankedOperation.__init__(self, Dap.DP_CTRLSTAT, data)
        
    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class SwdCtrlStat(SwdDpBankedOperation):
    def __init__(self, data = None):
        SwdDpBankedOperation.__init__(self, Dap.DP_CTRLSTAT, data)
        
    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class SwdRdBuff(Operation):
    def operations(self, dp):
        return [swd.Read(False, Dap.DP_RDBUFF)]

    def update(self, ops):
        self.data = ops[-1].data

class JtagRdBuff(Operation):
    def operations(self, dp):
        return [dp.port.cmd_dr_shift(JtagDp.DPACC, (Dap.DP_RDBUFF << 1) | 1, 35)]

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        self.data = ops[-1].tdo >> 3

class ApAccess(Operation):
    def __init__(self, is_read, addr, ap, be):
        self.is_read = is_read
        self.addr = addr
        self.ap = ap
        self.be = be

    def operations(self, dp):
        return dp.cmd_select(ap = self.ap, ap_bank = self.addr >> 4).operations(dp)

    def __repr__(self):
        if self.is_read:
            return "dap.ApRead(0x%x, %d, 0x%x)" % (self.addr, self.ap, self.be)
        else:
            return "dap.ApWrite(0x%x, 0x%x, %d, 0x%x)" % (self.addr, self.data, self.ap, self.be)

class SwdApRead(ApAccess):
    def __init__(self, addr, ap = 0, be = 0xf):
        ApAccess.__init__(self, True, addr, ap, be)

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        ret.append(swd.Read(True, (self.addr >> 2) & 3))

        return ret + dp.cmd_rdbuff().operations(dp)

    def update(self, ops):
        self.data = ops[-1].data

class SwdApWrite(ApAccess):
    def __init__(self, addr, data, ap = 0, be = 0xf):
        ApAccess.__init__(self, False, addr, ap, be)
        self.data = data

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        return ret + [swd.Write(True, (self.addr >> 2) & 3, self.data)]

class JtagApRead(ApAccess):
    def __init__(self, addr, ap = 0, be = 0xf):
        ApAccess.__init__(self, True, addr, ap, be)

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        ret.append(dp.port.cmd_dr_shift(JtagDp.APACC, ((self.addr >> 1) & 0x6) | 1, 35))
        ret.append(dp.port.cmd_run(40))

        return ret + dp.cmd_rdbuff().operations(dp)

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        self.data = ops[-1].tdo >> 3

class JtagApWrite(ApAccess):
    def __init__(self, addr, data, ap = 0, be = 0xf):
        ApAccess.__init__(self, False, addr, ap, be)
        self.data = data

    def operations(self, dp):
        ret = ApAccess.operations(self, dp)
        
        return ret + [dp.port.cmd_dr_shift(JtagDp.APACC, (self.data << 3) | ((self.addr >> 1) & 0x6), 35),
                      dp.port.cmd_run(40)]
