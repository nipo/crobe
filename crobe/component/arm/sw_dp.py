from ...protocol import swd
from ...part_id import PartId
from . import dp
from collections import deque
import math

parts = []
for model in (0xba, 0xbb, 0xbc):
    for version in (0, 1, 2):
        parts.append(PartId(4, 0x3b, (model << 8) | version))
        parts.append(PartId(4, 0x3b, (model << 8) | version | 0x10))

@swd.Interface.db.register(*parts)
class SwDp(dp.Dp):
    IDCODE   = 0 # R
    ABORT    = 0 # W
    RESEND   = 2 # R

    max_freq = 15e6

    def __init__(self, port):
        dp.Dp.__init__(self, "SW-DP", port)

    def start(self):
        self.port.freq_cap(self, self.max_freq)
        dp.Dp.start(self)
        
    def debug_enable(self, enable):
        self.abort(0x1f)
        dp.Dp.debug_enable(self, enable)
        
        if self.version >= 1 and not self.minimal and enable and self.port.turnaround_supported:
            self.dlcr = (self.dlcr & ~0x300) | 0x300
            self.port.turnaround_cycles = 4
        if self.minimal:
            self.port.freq_cap(self, 8e6)
        if enable:
            self.abort(0x1f)

    @property
    def idr(self):
        op = self.port.cmd_read(False, self.DPIDR)
        self.port.execute([self.port.cmd_write(False, self.ABORT, 0x1f), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)
        return op.data

    @property
    def idcode(self):
        return PartId.from_idcode(self.idr)

    def cmd_banked_reg_read(self, regno):
        op = self.port.cmd_read(False, regno & 0x3)
        if self.version < 1:
            assert regno & ~0x3 == 0
            return [op]
        else:
            return [self.port.cmd_write(False, self.SELECT, regno >> 2), op]

    def banked_reg_read(self, regno):
        op = self.port.cmd_read(False, regno & 0x3)
        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([op])
        else:
            self.port.execute([self.port.cmd_write(False, self.SELECT, regno >> 2), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)
        return op.data

    def banked_reg_write(self, regno, data):
        op = self.port.cmd_write(False, regno & 0x3, data)
        if self.version < 1:
            assert regno & ~0x3 == 0
            self.port.execute([op])
        else:
            self.port.execute([self.port.cmd_write(False, self.SELECT, regno >> 2), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)

    def abort(self, what = 0x1f):
        op = self.port.cmd_write(False, self.ABORT, what)
        self.port.execute([op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)

    def execute(self, operations):
        must_restart = True
        insert_run = 0
        while must_restart:
            must_restart = False

            ops = self.lower(operations, insert_run)
            self.port.execute(ops)

            #self.logger.debug("Done:")
            for i, o in enumerate(operations):
                if not isinstance(o, (dp.ApRead, dp.ApWrite)):
                    continue

                if isinstance(o, dp.ApWrite):
                    #self.logger.debug("- %d, %s, %s", i, o, o.__op.ack)
                    continue

                #self.logger.debug("- %d, %s -> %s %s 0x%08x", i, o, o.__value_op, o.__value_op.ack, o.__value_op.data)
                oo = o.__value_op

                if oo.ack == swd.Ack.OK:
                    o.data = oo.data
                    continue

                if oo.ack == swd.Ack.WAIT:
                    operations = list(operations)[i:]
                    self.abort(0x10)
                    must_restart = True
                    insert_run += 1
                    #self.logger.warning("Delaying subsequent operations by %d", insert_run)
                    break

                #self.logger.debug("Had an error, aborting")
                self.abort(0x15)
                raise dp.DpAccessFailure(o)

    def lower(self, operations, insert_run = 0):
        ops = deque()

        ap_read_pending = None
        select = 0
        select_dirty = True
        freq = self.port.freq

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
                    ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None

                ops.append(self.port.cmd_write(False, self.SELECT, select))
                select_dirty = False

            if isinstance(o, dp.ApRead):
                o.__op = self.port.cmd_read(True, (o.addr >> 2) & 3)
            else:
                o.__op = self.port.cmd_write(True, (o.addr >> 2) & 3, o.data)

            if ap_read_pending:
                if isinstance(o, dp.ApRead):
                    ap_read_pending.__value_op = o.__op
                else:
                    ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)

            if isinstance(o, dp.ApRead):
                ap_read_pending = o
            else:
                ap_read_pending = None
            ops.append(o.__op)

            c = insert_run + int(math.ceil(o.interval * float(freq)))
            if c:
                ops.append(self.port.cmd_run(c))

        if ap_read_pending:
            ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
            ops.append(ap_read_pending.__value_op)

        return ops
