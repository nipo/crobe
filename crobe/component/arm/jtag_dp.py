from ...adapter.protocol import jtag
from ...part_id import PartId
from . import dp
from enum import IntEnum

class JtagDp(dp.Dp):
    IDCODE  = 0xe
    DPACC   = 0xa
    APACC   = 0xb
    ABORT   = 0x8

    class Ack(IntEnum):
        OK = 2
        WAIT = 1
        INVALID = 3

    def __init__(self, port):
        dp.Dp.__init__(self, "JTAG-DP", port)

    def _cmd_shift(self, acc, a, d = None):
        rnw = 1 if d is None else 0
        return self.port.cmd_dr_shift(acc, ((d or 0) << 3) | ((a & 3) << 1) | rnw, 35)

    def _rsp_split(self, rsp):
        ack = rsp.tdo & 0x7
        ack = {2: self.Ack.OK, 1: self.Ack.WAIT}.get(ack, self.Ack.INVALID)
        data = rsp.tdo >> 3
        return ack, data

    @property
    def idcode(self):
        return PartId.from_idcode(self.port.dr_shift(self.IDCODE, 0, 32))

    @property
    def idr(self):
        cmd = self._cmd_shift(self.DPACC, self.DPIDR)
        rsp = self._cmd_shift(self.DPACC, self.SELECT, 0)

        self.port.execute([cmd, rsp])

        ack, data = self._rsp_split(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Read failed")

        return data

    def abort(self, what = 0x1):
        cmd = self._cmd_shift(self.ABORT, 0, what)
        self.port.execute([cmd])

    def banked_reg_read(self, regno):
        sel = self._cmd_shift(self.DPACC, self.SELECT, regno >> 2)
        cmd = self._cmd_shift(self.DPACC, regno)
        rsp = self._cmd_shift(self.DPACC, self.SELECT, 0)

        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([cmd, rsp])
        else:
            self.port.execute([sel, cmd, rsp])

        ack, data = self._rsp_split(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Read failed")

        return data

    def banked_reg_write(self, regno, data):
        sel = self._cmd_shift(self.DPACC, self.SELECT, regno >> 2)
        cmd = self._cmd_shift(self.DPACC, regno, data)
        rsp = self._cmd_shift(self.DPACC, self.SELECT, 0)

        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([cmd, rsp])
        else:
            self.port.execute([sel, cmd, rsp])

        ack, data = self._rsp_split(rsp)

        if ack != self.Ack.OK:
            raise dp.DpAccessFailure("Write failed")

    def execute(self, operations):
        must_restart = True
        insert_run = 0
        while must_restart:
            must_restart = False

            ops = self.lower(operations, insert_run)
            self.port.execute(ops)

            ack, ctrlstat = self._rsp_split(ops[-1])
            has_error = bool(ctrlstat & 0x20)

            self.logger.debug("Done:")
            for i, o in enumerate(operations):
                if not isinstance(o, dp.ApRead):
                    self.logger.debug("- %d, %s", i, o)
                    continue

                ack, data = self._rsp_split(o.__value_op)
                self.logger.debug("- %d, %s -> %s %s 0x%08x", i, o, o.__value_op, ack, data)

                if ack == self.Ack.OK:
                    o.data = data
                    continue

                if ack == self.Ack.WAIT:
                    operations = operations[i:]
                    self.ctrlstat = self.ctrlstat | 2
                    must_restart = True
                    insert_run += 1
                    self.logger.info("Delaying subsequent operations by %d", insert_run)
                    break

                self.abort()
                raise dp.DpAccessFailure("Invalid ACK")

            if has_error:
                self.ctrlstat = ctrlstat | 0x20
                raise dp.DpAccessFailure()

    def lower(self, operations, insert_run = 0):
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
                    ap_read_pending.__value_op = self._cmd_shift(self.DPACC, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None

                ops.append(self._cmd_shift(self.DPACC, self.SELECT, select))
                select_dirty = False

            if ap_read_pending:
                if isinstance(o, dp.ApRead):
                    ap_read_pending.__value_op = self._cmd_shift(self.APACC, o.addr >> 2)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = o
                else:
                    ap_read_pending.__value_op = self._cmd_shift(self.DPACC, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None
                    ops.append(self._cmd_shift(self.APACC, o.addr >> 2, o.data))
            else:
                if isinstance(o, dp.ApRead):
                    ops.append(self._cmd_shift(self.APACC, o.addr >> 2))
                    ap_read_pending = o
                else:
                    ops.append(self._cmd_shift(self.APACC, o.addr >> 2, o.data))

            ops.append(self.port.cmd_run(8 + insert_run))

        if ap_read_pending:
            self._cmd_shift(self.DPACC, self.RDBUFF)
            ap_read_pending.__value_op = self._cmd_shift(self.DPACC, self.CTRLSTAT)
            ops.append(ap_read_pending.__value_op)
        else:
            ops.append(self._cmd_shift(self.DPACC, self.CTRLSTAT))
        ops.append(self._cmd_shift(self.DPACC, self.CTRLSTAT))

        return ops

@jtag.Tap.db.register(PartId(4, 0x3b, 0xba00))
class JtagDpTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "JTAG-DP Tap"

    def start(self):
        self.child_add(JtagDp(self))
        jtag.Tap.start(self)
