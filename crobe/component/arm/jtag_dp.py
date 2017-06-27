from ...adapter.protocol import jtag
from ...part_id import PartId
from . import dp

class Operation:
    def __init__(self):
        pass

    def __repr__(self):
        return "dap.%s()" % (self.__class__.__name__)

    def update(self, ops):
        pass

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

class ApAccess(Operation):
    def __init__(self, is_read, addr, ap):
        self.is_read = is_read
        self.addr = addr
        self.ap = ap

    def operations(self, dp):
        return dp.cmd_select(ap = self.ap, ap_bank = self.addr >> 4).operations(dp)

    def __repr__(self):
        if self.is_read:
            return "dap.ApRead(0x%x, %d)" % (self.addr, self.ap)
        else:
            return "dap.ApWrite(0x%x, 0x%x, %d)" % (self.addr, self.data, self.ap)

class JtagDp(dp.Dp):
    IDCODE  = 0xe
    DPACC   = 0xa
    APACC   = 0xb
    ABORT   = 0x8

    def __init__(self, port):
        dp.Dp.__init__(self, "JTAG-DP", port)

    def cmd_idcode(self):
        return IdCode()

    def cmd_rdbuff(self):
        return RdBuff()

    def cmd_select(self, ap = None, ap_bank = None, dp_bank = None):
        return Select(ap, ap_bank, dp_bank)

    def cmd_abort(self, what = 0x1f):
        return Abort(what)

    def cmd_ctrl_stat(self, data = None):
        return CtrlStat(data)

    def cmd_ap_read(self, addr, ap = 0):
        return ApRead(addr, ap)

    def cmd_ap_write(self, addr, data, ap = 0):
        return ApWrite(addr, data, ap)

    def execute(self, operations):
        ops = []
        for o in operations:
            o.__ops = list(o.operations(self))
            ops += o.__ops

        self.port.execute(ops)

        self.logger.debug("Done:")
        for i, o in enumerate(operations):
            self.logger.debug("- %d, %s: %s", i, o, o.__ops)

        for i, o in enumerate(operations):
            try:
                o.update(o.__ops)
            except WaitError as e:
                self.logger.error("Failed at operation #%d", i)
                raise

@jtag.Tap.db.register(PartId(4, 0x3b, 0xba00))
class JtagDpTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "JTAG-DP Tap"

    def start(self):
        self.child_add(JtagDp(self))
        jtag.Tap.start(self)

class Idcode(Operation):
    def operations(self, port):
        return [port.port.cmd_dr_shift(JtagDp.IDCODE, 0, 32)]

    def update(self, ops):
        self.data = ops[-1].tdo

class Abort(Operation):
    def __init__(self, what = 0x1f):
        self.what = what

    def operations(self, port):
        return [port.port.cmd_dr_shift(JtagDp.ABORT, (self.what << 3) | 1, 35)]

    def __repr__(self):
        return "dap.Abort(0x%x)" % (self.what)

class Select(Select):
    def operations(self, port):
        data = self.data(port)
        if data is None:
            return []
        return [port.port.cmd_dr_shift(JtagDp.DPACC, (data << 3) | (dp.Dp.SELECT << 1), 35)]

class DpBankedOperation(DpBankedOperation):
    def operations(self, port):
        ret = port.cmd_select(dp_bank = self.address >> 2).operations(port)
        
        if self.is_read:
            return ret + [port.port.cmd_dr_shift(JtagDp.DPACC, ((self.address & 3) << 1) | 1, 35),
                          port.port.cmd_run(40),
                          port.port.cmd_dr_shift(JtagDp.DPACC, 1, 35)]
        else:
            return ret + [port.port.cmd_dr_shift(JtagDp.DPACC, (self.data << 3) | ((self.address & 3) << 1), 35)]

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        if self.is_read:
            self.data = ops[-1].tdo >> 3

class CtrlStat(DpBankedOperation):
    def __init__(self, data = None):
        DpBankedOperation.__init__(self, dp.Dp.CTRLSTAT, data)
        
    def __repr__(self):
        if self.is_read:
            return "dap.CtrlStat()"
        else:
            return "dap.CtrlStat(0x%x)" % self.data

class RdBuff(Operation):
    def operations(self, port):
        return [port.port.cmd_dr_shift(JtagDp.DPACC, (dp.Dp.RDBUFF << 1) | 1, 35)]

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        self.data = ops[-1].tdo >> 3

class ApRead(ApAccess):
    def __init__(self, addr, ap = 0):
        ApAccess.__init__(self, True, addr, ap)

    def operations(self, port):
        ret = ApAccess.operations(self, port)
        
        ret.append(port.port.cmd_dr_shift(JtagDp.APACC, ((self.addr >> 1) & 0x6) | 1, 35))
        ret.append(port.port.cmd_run(40))

        return ret + port.cmd_rdbuff().operations(port)

    def update(self, ops):
        if ops[-1].tdo & 7 != 2:
            raise WaitError()
        self.data = ops[-1].tdo >> 3

class ApWrite(ApAccess):
    def __init__(self, addr, data, ap = 0):
        ApAccess.__init__(self, False, addr, ap)
        self.data = data

    def operations(self, port):
        ret = ApAccess.operations(self, port)
        
        return ret + [port.port.cmd_dr_shift(JtagDp.APACC, (self.data << 3) | ((self.addr >> 1) & 0x6), 35),
                      port.port.cmd_run(40)]
