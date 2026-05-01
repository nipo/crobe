"""JTAG TAP-state walker driven by a (TMS, TDI) bit stream.

Used by remote bit-bang protocols (XVC, JoP, ...) where the network
peer drives JTAG at the TMS/TDI level and we need to translate that
stream into :class:`crobe.protocol.jtag.Interface` ops.

The walker mirrors the JTAG state machine per input bit. On state
transitions, it decides what the just-completed run of bits represented
(a Shift-DR/IR segment, an idle run in RTI, a TAP reset, a Capture-only
transit) and queues the corresponding interface op. Captured TDO bits
are spliced back into a same-length output vector aligned with the
input.

The instance keeps state across calls — peers may drip-feed bits, and a
stream may end mid-Shift or mid-RTI. The next call resumes from where
the previous one left off.
"""

from ..bitstring import BitString
from ..protocol import jtag


class JtagTmsWalker:
    """Process (TMS, TDI) bit pairs against the JTAG TAP state machine
    and queue resulting ops on a :class:`crobe.protocol.jtag.Interface`.

    State indexing collapses the DR/IR mirror sides into a single set
    (Capture/Shift/...); :attr:`_in_ir` records which side we entered
    on the last Capture transition.
    """

    TLR     = 0   # Test-Logic-Reset
    RTI     = 1   # Run-Test/Idle
    SEL_DR  = 2
    SEL_IR  = 3
    CAPTURE = 4
    SHIFT   = 5
    EXIT1   = 6
    PAUSE   = 7
    EXIT2   = 8
    UPDATE  = 9

    NAMES = ["TLR", "RTI", "Sel-DR", "Sel-IR",
             "Capture", "Shift", "Exit1", "Pause", "Exit2", "Update"]

    # NEXT_STATE[tms][current] -> next
    NEXT_STATE = (
        (RTI, RTI, CAPTURE, CAPTURE, SHIFT, SHIFT, PAUSE, PAUSE, SHIFT, RTI),
        (TLR, SEL_DR, SEL_IR, TLR, EXIT1, EXIT1, UPDATE, EXIT2, UPDATE, SEL_DR),
    )

    def __init__(self, interface):
        self._interface = interface
        self._state = self.TLR
        self._in_ir = False

    @property
    def state(self):
        return self._state

    @property
    def state_name(self):
        return self.NAMES[self._state]

    def process(self, tms, tdi):
        """Walk one batch of TMS+TDI bits, drive the interface, return TDO.

        ``tms`` and ``tdi`` must be equal-length :class:`BitString`. The
        returned BitString has the same length; bits captured during a
        Shift segment are populated, all other positions are zero.
        """
        if len(tms) != len(tdi):
            raise ValueError(
                f"tms/tdi length mismatch: {len(tms)} vs {len(tdi)}")
        n = len(tms)
        if n == 0:
            return BitString()

        # If the previous call ended mid-Shift (peer drip-feeding bits),
        # the first bit of this call belongs to the same Shift run.
        # Same for an in-progress RTI run.
        shift_start = 0 if self._state == self.SHIFT else None
        run_start = 0 if self._state == self.RTI else None

        ops = []
        # (op, output_start, output_end) for shifts, so TDO can be spliced.
        shift_slots = []

        for i in range(n):
            tms_bit = int(tms[i])
            next_state = self.NEXT_STATE[tms_bit][self._state]

            # Leaving Shift: emit the accumulated segment. The current
            # bit is the boundary TMS=1 bit; cmd_shift consumes it as
            # part of the segment and handles the Exit1 transition.
            if self._state == self.SHIFT and next_state != self.SHIFT:
                segment = tdi[shift_start:i + 1]
                op = self._interface.cmd_shift(segment, read_tdo=True)
                ops.append(op)
                shift_slots.append((op, shift_start, i + 1))
                shift_start = None

            # Leaving RTI: flush accumulated run cycles.
            if (self._state == self.RTI and next_state != self.RTI
                    and run_start is not None):
                cycles = i - run_start
                if cycles > 0:
                    ops.append(self._interface.cmd_run(cycles))
                run_start = None

            # Leaving TLR: align target FSM with the peer's view.
            if self._state == self.TLR and next_state != self.TLR:
                ops.append(self._interface.cmd_tap_reset())

            # Entering Capture: choose IR or DR side.
            if next_state == self.CAPTURE:
                self._in_ir = (self._state == self.SEL_IR)
                if self._in_ir:
                    ops.append(self._interface.cmd_capture_ir())
                else:
                    ops.append(self._interface.cmd_capture_dr())

            # Entering Shift: the bit at position i is the Cap->Shift
            # (or Ex2->Shift) state-transition edge. Per JTAG spec, no
            # shift action happens on that edge — shifting only fires
            # on TCKs whose pre-edge state is already Shift. The first
            # actual shift bit is at i+1.
            if next_state == self.SHIFT and self._state != self.SHIFT:
                shift_start = i + 1

            # Entering RTI: start a run counter.
            if next_state == self.RTI and self._state != self.RTI:
                run_start = i

            self._state = next_state

        # End-of-input: flush any in-progress segment.
        if (self._state == self.SHIFT
                and shift_start is not None and shift_start < n):
            segment = tdi[shift_start:n]
            op = self._interface.cmd_shift(segment, read_tdo=True)
            ops.append(op)
            shift_slots.append((op, shift_start, n))

        if (self._state == self.RTI
                and run_start is not None and run_start < n):
            ops.append(self._interface.cmd_run(n - run_start))

        if ops:
            self._interface.execute(ops)

        # Reassemble TDO bit-aligned with input.
        if not shift_slots:
            return BitString(0, n)
        tdo = BitString()
        cursor = 0
        for op, start, end in shift_slots:
            if start > cursor:
                tdo += BitString(0, start - cursor)
            tdo += op.tdo
            cursor = end
        if cursor < n:
            tdo += BitString(0, n - cursor)
        return tdo
