from . import svf
import binascii
from ..bitstring import BitString
import warnings

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
    def run(self, svf):
        for op in svf:
            self.handle(op)
        self.flush()

class ChainPlayer(Player):
    def __init__(self, chain):
        self.intf = chain.port

        self.ir = Context()
        self.dr = Context()
        self.pending = [self.intf.cmd_tap_reset(),
                        self.intf.cmd_run(0)]
        self.state = "idle"

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
            self.test_run(op)
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
            ctdo = int(ctx.tdo)
            if ctx.tdo:
                tdo &= int(ctx.mask)
                ctdo &= int(ctx.mask)
            if tdo != ctdo:
                raise ValueError("Expected TDO:%r/%r, had %r" % (ctx.tdo, ctx.mask, op.tdo))

        self.move_to(ctx.end_state)

    def flush(self):
        self.intf.execute(self.pending)
        self.pending = []

    def test_run(self, op):
        self.move_to(op.run_state)
        if op.run_state == "idle" or not op.run_state:
            clocks = [0]
            if op.run_count:
                clocks.append(op.run_count)
            if op.tck:
                clocks.append(op.tck)
            if op.min_time:
                clocks.append(self.freq * op.min_time)
            self.pending.append(self.intf.cmd_run(max(clocks)))
        self.move_to(op.end_state)

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
        self.tap.port.freq_cap("svf", f)

class TapRegContext:
    def __init__(self, player):
        self.tdi = BitString()
        self.tdo = BitString()
        self.mask = BitString()
        self.update = False
        self.player = player

    def shift(self, tdi, tdo, mask):
        l = len(tdi or tdo)

        self.tdi += tdi if tdi else BitString(0, l)
        self.tdo += tdo if tdo else BitString(0, l)
        self.mask += mask if mask else BitString(-1 if tdo else 0, l)
        if self.update:
            self.run()

    def run(self):
        if not self.tdi and not self.tdo:
            return

        rb = bool(int(self.mask))
        cmd = self._cmd(rb)
        self.player.pending.append(cmd)
        if rb:
            self.player.flush()

            print("Expected :", str(binascii.b2a_hex(bytes(self.tdo)), "ascii"))
            print("Actual   :", str(binascii.b2a_hex(bytes(cmd.tdo)), "ascii"))

            tdo = int(cmd.tdo)
            ctdo = int(self.tdo)
            if self.mask:
                tdo &= int(self.mask)
                ctdo &= int(self.mask)
            if tdo != ctdo:
                raise ValueError(self.__class__.__name__ + " Expected TDO:%r/%r, had %r" % (self.tdo, self.mask, cmd.tdo))

        self.tdi = BitString()
        self.tdo = BitString()
        self.mask = BitString()

class TapIrContext(TapRegContext):
    def _cmd(self, rb):
        irlen = self.player.tap.irlen
        tdi = self.tdi[-irlen:]
        assert len(tdi) == irlen
        return self.player.tap.cmd_dr_shift(int(tdi), None,
                                            read_ir = rb,
                                            return_type = (lambda x:BitString(x, irlen)) if rb else None)

class TapDrContext(TapRegContext):
    def _cmd(self, rb):
        return self.player.tap.cmd_dr_shift(None,
                                            self.tdi or None,
                                            read_tdo = rb)

class TapPlayer(Player):
    def __init__(self, tap):
        self.tap = tap

        self.ir = TapIrContext(self)
        self.dr = TapDrContext(self)
        self.pending = [tap.cmd_run(0)]

    def flush(self):
        self.tap.execute(self.pending)
        self.pending = []

    def handle(self, op):
        if isinstance(op, (svf.TrailerDr,
                           svf.TrailerIr,
                           svf.HeaderDr,
                           svf.HeaderIr)):
            pass
        elif isinstance(op, svf.ShiftDr):
            self.ir.run()
            self.dr.shift(op.tdi, op.tdo, op.mask)
        elif isinstance(op, svf.ShiftIr):
            self.ir.run()
            self.dr.run()
            self.ir.shift(op.tdi, op.tdo, op.mask)
        elif isinstance(op, svf.State):
            if op.states == ["idle"]:
                self.pending.append(self.tap.cmd_run(0))
            else:
                warnings.warn("State change ignored %s" % op.states)
        elif isinstance(op, svf.Trst):
            warnings.warn("Tap reset ignored")
        elif isinstance(op, svf.EndDr):
            self.dr.update = op.end_state != "drpause"
        elif isinstance(op, svf.EndIr):
            self.ir.update = op.end_state != "irpause"
        elif isinstance(op, svf.RunTest):
            self.test_run(op)
        elif isinstance(op, svf.Frequency):
            self.flush()
            self.tap.port.port.freq_cap("svf", op.value)
        else:
            raise NotImplementedError("Unknown operation", op)

    def test_run(self, op):
        clocks = [0]
        self.ir.run()
        self.dr.run()
        if op.run_count:
            clocks.append(op.run_count)
        if op.tck:
            clocks.append(op.tck)
        if op.min_time:
            clocks.append(int(self.tap.port.port.freq * op.min_time))
        self.pending.append(self.tap.cmd_run(max(clocks)))
