from ...protocol import jtag
from ...util.pretty import metric
from ...part_id import PartId
from . import dp
from enum import IntEnum

class JtagDp(dp.Dp):
    """
    Adapter between DP operations and JTAG Tap.
    """
    def __init__(self, port):
        dp.Dp.__init__(self, "JTAG-DP", port)

    def freq_update(self, freq):
        self.logger.debug("Max AP freq changed to %s", metric(freq, "Hz"))
        self.port.max_freq = freq
        self.port.port.children_changed()
        return freq

    @property
    def idcode(self):
        return PartId.from_idcode(self.port.IDCODE.shift(0))

    @property
    def idr(self):
        cmd = self.port.DPACC.cmd(self.__pack(self.DPIDR))
        rsp = self.port.DPACC.cmd(self.__pack(self.SELECT, 0))

        self.port.execute([cmd, rsp])

        ack, data = self.__unpack(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Read failed")

        return data

    class Ack(IntEnum):
        OK = 2
        WAIT = 1
        INVALID = 3

    def __pack(self, a, d = None):
        rnw = 1 if d is None else 0
        return ((d or 0) << 3) | ((a & 3) << 1) | rnw

    def __unpack(self, rsp):
        ack = rsp.tdo & 0x7
        ack = {2: self.Ack.OK, 1: self.Ack.WAIT}.get(ack, self.Ack.INVALID)
        data = rsp.tdo >> 3
        return ack, data

    def abort(self, what = 0x1):
        self.port.ABORT.shift(what << 3)

    def banked_reg_read(self, regno):
        sel = self.port.DPACC.cmd(self.__pack(self.SELECT, regno >> 2))
        cmd = self.port.DPACC.cmd(self.__pack(regno))
        rsp = self.port.DPACC.cmd(self.__pack(self.SELECT, 0))

        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([cmd, rsp])
        else:
            self.port.execute([sel, cmd, rsp])

        ack, data = self.__unpack(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Read failed")

        return data

    def banked_reg_write(self, regno, data):
        sel = self.port.DPACC.cmd(self.__pack(self.SELECT, regno >> 2))
        cmd = self.port.DPACC.cmd(self.__pack(regno, data))
        rsp = self.port.DPACC.cmd(self.__pack(self.SELECT, 0))

        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([cmd, rsp])
        else:
            self.port.execute([sel, cmd, rsp])

        ack, data = self.__unpack(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Write failed")

    def execute(self, operations):
        must_restart = True
        insert_run = 0
        while must_restart:
            must_restart = False

            ops = self.__lower(operations, insert_run)
            self.port.execute(ops)

            ack, ctrlstat = self.__unpack(ops[-1])
            has_error = bool(ctrlstat & 0x20)

            self.logger.trace("Done:")
            for i, o in enumerate(operations):
                if not isinstance(o, dp.ApRead):
                    self.logger.trace("- %d, %s", i, o)
                    continue

                ack, data = self.__unpack(o.__value_op)
                self.logger.trace("- %d, %s -> %s %s 0x%08x", i, o, o.__value_op, ack, data)

                if ack == self.Ack.OK:
                    o.data = data
                    continue

                if ack == self.Ack.WAIT:
                    operations = list(operations)[i:]
                    self.ctrlstat = self.ctrlstat | 2
                    must_restart = True
                    insert_run += 1
                    self.logger.trace("Delaying subsequent operations by %d", insert_run)
                    break

                self.abort()
                raise dp.DpAccessFailure("Invalid ACK")

            if has_error:
                self.ctrlstat = ctrlstat | 0x20
                raise dp.DpAccessFailure()

    def __lower(self, operations, insert_run = 0):
        ops = []

        ap_read_pending = None
        select = 0
        select_dirty = True

        for o in operations:
            if isinstance(o, dp.Run):
                ops.append(self.port.cmd_run(o.cycles))
                continue

            assert isinstance(o, (dp.ApWrite, dp.ApRead))

            if o.ap != select >> 24:
                select = (select & 0xff) | (o.ap << 24)
                select_dirty = True

            if o.addr >> 4 != (select >> 4) & 0xf:
                select = (select & ~0xf0) | (o.addr & 0xf0)
                select_dirty = True

            if select_dirty:
                if ap_read_pending:
                    ap_read_pending.__value_op = self.port.DPACC.cmd(self.__pack(self.RDBUFF))
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None

                ops.append(self.port.DPACC.cmd(self.__pack(self.SELECT, select)))
                select_dirty = False

            if ap_read_pending:
                if isinstance(o, dp.ApRead):
                    ap_read_pending.__value_op = self.port.APACC.cmd(self.__pack(o.addr >> 2))
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = o
                else:
                    ap_read_pending.__value_op = self.port.DPACC.cmd(self.__pack(self.RDBUFF))
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None
                    ops.append(self.port.APACC.cmd(self.__pack(o.addr >> 2, o.data)))
            else:
                if isinstance(o, dp.ApRead):
                    ops.append(self.port.APACC.cmd(self.__pack(o.addr >> 2)))
                    ap_read_pending = o
                else:
                    ops.append(self.port.APACC.cmd(self.__pack(o.addr >> 2, o.data)))

            ops.append(self.port.cmd_run(8 + insert_run))

        if ap_read_pending:
            self.port.DPACC.cmd(self.__pack(self.RDBUFF))
            ap_read_pending.__value_op = self.port.DPACC.cmd(self.__pack(self.CTRLSTAT))
            ops.append(ap_read_pending.__value_op)
        else:
            ops.append(self.port.DPACC.cmd(self.__pack(self.CTRLSTAT)))
        ops.append(self.port.DPACC.cmd(self.__pack(self.CTRLSTAT)))

        return ops

@jtag.Chain.db.register(PartId(4, 0x3b, 0xba00))
@jtag.Chain.db.register(PartId(4, 0x3b, 0xba01))
class JtagDpTap(jtag.Tap):
    """JTAG-DP TAP.
    
    Other instructions may be vendor-defined. Then SoC-specific TAPs
    may inherit this TAP definition for adding their stuff.

    """
    irlen = 4
    max_freq = 20e6

    DP_REG = jtag.Dr(35)
    AP_REG = jtag.Dr(35)
    ABORT_REG = jtag.Dr(35)
    
    IDCODE               = jtag.Instruction(0xe, "DEVICE_ID")
    DPACC                = jtag.Instruction(0xa, "DP_REG")
    APACC                = jtag.Instruction(0xb, "AP_REG")
    ABORT                = jtag.Instruction(0x8, "ABORT_REG")

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "JTAG-DP Tap"
        self.child_add(JtagDp(self))
