import enum
from .. import bitstring

class State(enum.Enum):
    Reset       = enum.auto()
    RunTestIdle = enum.auto()
    SelectDr    = enum.auto()
    SelectIr    = enum.auto()
    CaptureDr   = enum.auto()
    CaptureIr   = enum.auto()
    ShiftDr     = enum.auto()
    ShiftIr     = enum.auto()
    Exit1Dr     = enum.auto()
    Exit1Ir     = enum.auto()
    PauseDr     = enum.auto()
    PauseIr     = enum.auto()
    Exit2Dr     = enum.auto()
    Exit2Ir     = enum.auto()
    UpdateDr    = enum.auto()
    UpdateIr    = enum.auto()

class ChainSimulator:
    NEXT_STATE = {
        State.Reset:  (State.RunTestIdle, State.Reset),
        State.RunTestIdle:  (State.RunTestIdle, State.SelectDr),
        State.SelectDr:  (State.CaptureDr, State.SelectIr),
        State.SelectIr:  (State.CaptureIr, State.Reset),
        State.CaptureDr:  (State.ShiftDr, State.Exit1Dr),
        State.CaptureIr:  (State.ShiftIr, State.Exit1Ir),
        State.ShiftDr:  (State.ShiftDr, State.Exit1Dr),
        State.ShiftIr:  (State.ShiftIr, State.Exit1Ir),
        State.Exit1Dr:  (State.PauseDr, State.UpdateDr),
        State.Exit1Ir:  (State.PauseIr, State.UpdateIr),
        State.PauseDr:  (State.PauseDr, State.Exit2Dr),
        State.PauseIr:  (State.PauseIr, State.Exit2Ir),
        State.Exit2Dr:  (State.ShiftDr, State.UpdateDr),
        State.Exit2Ir:  (State.ShiftIr, State.UpdateIr),
        State.UpdateDr:  (State.RunTestIdle, State.SelectDr),
        State.UpdateIr:  (State.RunTestIdle, State.SelectDr),
    }

    def __init__(self):
        self.state = State.Reset
        self.run_length = 0
        self.shreg = None
        
    def handle(self, tms, tdi):
        assert len(tms) == len(tdi)

        tdo = bitstring.BitString(0, 0)
        
        for point in range(len(tms)):
            state = self.state

            m = tms[point]
            i = tdi[point]

            next_state = self.NEXT_STATE[state][m]
            if state == next_state:
                self.run_length += 1
            else:
                if state == State.RunTestIdle:
                    self.run(self.run_length)
                elif state == State.Reset:
                    self.reset(self.run_length)
                self.run_length = 1

            if state == State.CaptureIr:
                self.shreg = self.capture_ir()
            elif state == State.CaptureDr:
                self.shreg = self.capture_dr()
            elif state == State.UpdateIr:
                self.update_ir(self.shreg)
            elif state == State.UpdateDr:
                self.update_dr(self.shreg)

            if state in [State.ShiftIr, State.ShiftDr]:
                tdo += bitstring.BitString(self.shreg[0], 1)
                self.shreg = self.shreg[1:] + bitstring.BitString(i, 1)
            else:
                tdo += bitstring.BitString(0, 1)

            self.state = next_state
                
    def capture_dr(self):
        return bitstring.BitString(0, 1)

    def capture_ir(self):
        return bitstring.BitString(1, 2)

    def update_dr(self, dr):
        ...

    def update_ir(self, ir):
        ...

    def run(self, cycles):
        ...

    def reset(self, cycles):
        ...
