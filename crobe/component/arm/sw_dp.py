from ...adapter.protocol import swd
from ...part_id import PartId
from . import dp

class SwDp(dp.Dp):
    IDCODE   = 0 # R
    ABORT    = 0 # W
    RESEND   = 2 # R
    
    def __init__(self, port, minimal, version):
        name = "SW-DPv%d" % version
        dp.Dp.__init__(self, name, port)
        self.minimal = minimal
        self.version = version

        if minimal:
            self.logger.info("Is a minimal implementation")

    def debug_enable(self, enable):
        dp.Dp.debug_enable(self, enable)

        if self.version >= 1 and not self.minimal and enable:
            self.dlcr = (self.dlcr & ~0x300) | 0x300
            self.port.turnaround_cycles = 4
            
    @property
    def idcode(self):
        op = self.port.cmd_read(False, self.IDCODE)
        self.port.execute([op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)
        return op.data

    @property
    def ctrlstat(self):
        op = self.port.cmd_read(False, self.CTRLSTAT)
        self.port.execute([self.port.cmd_write(False, self.SELECT, self.CTRLSTAT >> 2), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)
        return op.data

    @ctrlstat.setter
    def ctrlstat(self, data):
        op = self.port.cmd_write(False, self.CTRLSTAT, data)
        self.port.execute([self.port.cmd_write(False, self.SELECT, self.CTRLSTAT >> 2), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)

    @property
    def dlcr(self):
        op = self.port.cmd_read(False, self.DLCR)
        self.port.execute([self.port.cmd_write(False, self.SELECT, self.DLCR >> 2), op])
        if op.ack != swd.Ack.OK:
            raise dp.DpAccessFailure(op.ack)
        return op.data

    @dlcr.setter
    def dlcr(self, data):
        op = self.port.cmd_write(False, self.DLCR, data)
        self.port.execute([self.port.cmd_write(False, self.SELECT, self.DLCR >> 2), op])
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

            self.logger.debug("Done:")
            for i, o in enumerate(operations):
                if not isinstance(o, dp.ApRead):
                    self.logger.debug("- %d, %s", i, o)
                    continue

                self.logger.debug("- %d, %s -> %s %s 0x%08x", i, o, o.__value_op, o.__value_op.ack, o.__value_op.data)
                oo = o.__value_op

                if oo.ack == swd.Ack.OK:
                    o.data = oo.data
                    continue

                if oo.ack == swd.Ack.WAIT:
                    operations = operations[i:]
                    self.abort(0x10)
                    must_restart = True
                    insert_run += 1
                    self.logger.info("Delaying subsequent operations by %d", insert_run)
                    break

                raise dp.DpAccessFailure(o)

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
                    ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None

                ops.append(self.port.cmd_write(False, self.SELECT, select))
                select_dirty = False

            if ap_read_pending:
                if isinstance(o, dp.ApRead):
                    ap_read_pending.__value_op = self.port.cmd_read(True, (o.addr >> 2) & 3)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = o
                else:
                    ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
                    ops.append(ap_read_pending.__value_op)
                    ap_read_pending = None
                    ops.append(self.port.cmd_write(True, (o.addr >> 2) & 3, o.data))
            else:
                if isinstance(o, dp.ApRead):
                    ops.append(self.port.cmd_read(True, (o.addr >> 2) & 3))
                    ap_read_pending = o
                else:
                    ops.append(self.port.cmd_write(True, (o.addr >> 2) & 3, o.data))

            if insert_run:
                ops.append(self.port.cmd_run(insert_run))
                    
        if ap_read_pending:
            ap_read_pending.__value_op = self.port.cmd_read(False, self.RDBUFF)
            ops.append(ap_read_pending.__value_op)

        return ops

for model in (0xba, 0xbb, 0xbc):
    for version in (0, 1, 2):
        base = (model << 8) | version
        swd.Interface.db.register(PartId(4, 0x3b, base))(lambda port: SwDp(port, False, version))
        swd.Interface.db.register(PartId(4, 0x3b, base | 0x10))(lambda port: SwDp(port, True, version))
