from . import svf

class Context:
    def __init__(self):
        self.end_state = "idle"
        self.header = None
        self.trailer = None
        self.mask = None
        self.smask = None
        self.tdo = None
        self.tdi = None

    def trailer_update(self, op):
        if op.tdi:
            self.trailer = op.tdi

    def header_update(self, op):
        if op.tdi:
            self.header = op.tdi

    def shift_update(self, op):
        if op.tdi:
            self.tdi = op.tdi
        self.tdo = op.tdo

        if op.mask:
            self.mask = op.mask
        elif self.mask and len(self.mask) != len(self.tdi):
            self.mask = None

        if op.smask:
            self.smask = op.smask
        elif self.smask and len(self.smask) != len(self.tdi):
            self.smask = None

class Player:
    def __init__(self, svf, intf):
        self.svf = svf
        self.intf = intf

        self.ir = Context()
        self.dr = Context()
        self.pending = [intf.cmd_tap_reset(), intf.cmd_run(0)]
        self.state = "idle"

    def run(self):
        for op in self.svf:
            self.handle(op)
        self.flush()

    def handle(self, op):
        if isinstance(op, svf.TrailerDr):
            self.dr.trailer_update(op)
        elif isinstance(op, svf.TrailerIr):
            self.ir.trailer_update(op)
        elif isinstance(op, svf.HeaderDr):
            self.dr.header_update(op)
        elif isinstance(op, svf.HeaderIr):
            self.ir.header_update(op)
        elif isinstance(op, svf.ShiftDr):
            self.dr.shift_update(op)
            self.move_to("drcapture")
            self.shift(self.dr)
        elif isinstance(op, svf.ShiftIr):
            self.ir.shift_update(op)
            self.move_to("ircapture")
            self.shift(self.ir)
        elif isinstance(op, svf.State):
            for s in op.states:
                self.move_to(s)
        elif isinstance(op, svf.Trst):
            self.flush()
            self.trst_set(op.value == "on")
        elif isinstance(op, svf.EndDr):
            self.dr.end_state = op.end_state
        elif isinstance(op, svf.EndIr):
            self.ir.end_state = op.end_state
        elif isinstance(op, svf.RunTest):
            self.test_run(run_state = op.run_state,
                          run_count = op.run_count,
                          run_clock = op.run_clock,
                          end_state = op.end_state)
        elif isinstance(op, svf.Frequency):
            self.freq(op.value)
        else:
            raise NotImplementedError("Unknown operation", op)

    def shift(self, ctx):
        assert ctx.tdi

        assert self.state.endswith("capture") or self.state.endswith("pause")
        self.state = self.state[:2]+"pause"

        if ctx.header:
            self.pending.append(self.intf.cmd_shift(ctx.header, read_tdo = False))
        op = self.intf.cmd_shift(ctx.tdi, read_tdo = ctx.tdo is not None)
        self.pending.append(op)
        if ctx.trailer:
            self.pending.append(self.intf.cmd_shift(ctx.trailer, read_tdo = False))

        if ctx.tdo:
            self.flush()

            tdo = int(op.tdo)
            if ctx.mask:
                tdo &= int(ctx.mask)
            if tdo != int(ctx.tdo) & int(ctx.mask):
                raise ValueError("Expected TDO:%r/%r, had %r" % (ctx.tdo, ctx.mask, op.tdo))

        self.move_to(ctx.end_state)

    def flush(self):
        self.intf.execute(self.pending)
        self.pending = []

    def test_run(self, run_state, run_count, run_clock, end_state):
        self.move_to(run_state)
        if run_state == "idle" or not run_state:
            self.pending.append(self.intf.cmd_run(run_count))
        self.move_to(end_state)

    def move_to(self, state):
        if state == self.state:
            return

        if state == "ircapture":
            if self.state in ("idle", "drpause", "irpause"):
                self.pending.append(self.intf.cmd_capture_ir())
                self.state = state
            else:
                raise ValueError(self.state)
        elif state == "drcapture":
            if self.state in ("idle", "drpause", "irpause"):
                self.pending.append(self.intf.cmd_capture_dr())
                self.state = state
            else:
                raise ValueError(self.state)
        elif state == "run":
            if self.state in ("drpause", "irpause"):
                self.pending.append(self.intf.cmd_run(0))
                self.state = state
            else:
                raise ValueError(self.state)
        elif state in ("irupdate", "drupdate"):
            if self.state in ("drpause", "irpause"):
                self.pending.append(self.intf.cmd_run(0))
                self.state = state
            else:
                raise ValueError(self.state)
        elif state == "reset":
            self.pending.append(self.cmd_tap_reset())
            self.state = state

    def trst_set(self, enable):
        self.flush()
        self.intf.trst = enable

    def freq(self, f):
        self.flush()
        self.intf.freq = f
