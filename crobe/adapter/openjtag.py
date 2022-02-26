from .. import model
from .. import bitstring
from ..protocol import jtag, base
from collections import deque
import enum
import math

class State(enum.IntEnum):
    Reset     = 0
    Idle      = 1
    SelectDr  = 2
    CaptureDr = 3
    ShiftDr   = 4
    Exit1Dr   = 5
    PauseDr   = 6
    Exit2Dr   = 7
    UpdateDr  = 8
    SelectIr  = 9
    CapureIr  = 10
    ShiftIr   = 11
    Exit1Ir   = 12
    PauseIr   = 13
    Exit2Ir   = 14
    UpdateIr  = 15

class Operation:
    response_size = 0

    def __init__(self, parameter = 0, data = b''):
        self.parameter = parameter
        self.data = data

    def __bytes__(self):
        return bytes([(int(self.parameter) << 4) | self.command]) + self.data

    def decode(self, data):
        return None

    def __str__(self):
        return "<%s %s>" % (self.__class__.__name__, self.parameter)

    def __repr__(self):
        return str(self)
    
class DivisorSet(Operation):
    command =  0
    response_size = 0

    def __init__(self, divisor, adaptive = False):
        assert 1 <= divisor <= 8
        super().__init__(((divisor - 1) << 1) | int(adaptive))

class StateSet(Operation):
    command =  1
    response_size = 0

    def __init__(self, state):
        assert isinstance(state, State)
        super().__init__(state)

class StateGet(Operation):
    command =  2
    response_size = 1

    def __init__(self):
        super().__init__()

    def decode(self, data):
        return State(data[0] & 0xf)

class TlrReset(Operation):
    command =  3
    response_size = 0

    def __init__(self):
        super().__init__()

class TrstReset(Operation):
    command =  4
    response_size = 0

    def __init__(self, cycles = 1):
        assert 1 <= cycles <= 16
        super().__init__(cycles - 1)

class EndianSet(Operation):
    command =  5
    response_size = 0

    def __init__(self, little = True):
        super().__init__(int(little))

class ScanInOut(Operation):
    command =  6
    response_size = 1

    def __init__(self, bs, exit = False):
        assert 1 <= len(bs) <= 8
        self.length = len(bs)
        super().__init__(int(exit) | ((len(bs) - 1) << 1), bytes(bs))

    def decode(self, data):
        return bitstring.BitString(data[0], self.length)

class Run(Operation):
    command =  7
    response_size = 0

    def __init__(self, cycles):
        assert 1 <= cycles <= 16
        super().__init__(cycles - 1)

class OpenJtag(model.PortComponent):
    def __init__(self, port, base_freq = 48e6):
        super().__init__(port, "openjtag")
        self.base_freq = base_freq
        self.__divisor_dirty = True
        self.__divisor = 8
        self.__endianness_dirty = True
        self.__shift = None
        self.__pause = None
        self.__idle = True

    def freq_set(self, freq):
        div = math.ceil(self.base_freq / (freq or 48e6))
        div = min(8, max(1, div))
        if self.__divisor != div:
            self.__divisor = div
            self.__divisor_dirty = True
        return self.base_freq / self.__divisor
        
    def jtag_execute(self, operation_list):
        operation_list = list(operation_list)
        commands = []
        rsp_offsets = {}


        if self.__divisor_dirty:
            commands.append(DivisorSet(self.__divisor))
            self.__divisor_dirty = False

        if self.__endianness_dirty:
            commands.append(EndianSet(little = True))
            self.__endianness_dirty = False

        for index, op in enumerate(operation_list):
            if isinstance(op, jtag.CaptureDr):
                commands.append(StateSet(State.PauseDr))
                self.__shift = State.ShiftDr
                self.__pause = State.PauseDr
                self.__idle = False

            elif isinstance(op, jtag.CaptureIr):
                commands.append(StateSet(State.PauseIr))
                self.__shift = State.ShiftIr
                self.__pause = State.PauseIr
                self.__idle = False

            elif isinstance(op, jtag.Reset):
                commands.append(TlrReset())
                self.__idle = False

            elif isinstance(op, base.Reset):
                pass

            elif isinstance(op, jtag.Run):
                if not self.__idle:
                    commands.append(StateSet(State.Idle))
                self.__idle = True

                cycles = op.cycles
                while cycles > 8:
                    commands.append(Run(min(8, cycles)))
                    cycles -= 8

            elif isinstance(op, jtag.SwdToJtag):
                pass

            elif isinstance(op, jtag.Shift):
                commands.append(StateSet(self.__shift))
                tdi = op.tdi
                if isinstance(tdi, int):
                    tdi = bitstring.BitString(0, tdi)
                parts = []
                for off in range(0, len(tdi), 8):
                    end = min(off + 8, len(tdi))
                    s = ScanInOut(tdi[off:end], end == len(tdi))
                    parts.append(s)
                    commands.append(s)
                commands.append(StateSet(self.__pause))
                rsp_offsets[index] = parts
                self.__idle = False

            else:
                raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

        self.openjtag_execute(commands)

        for i, os in rsp_offsets.items():
            op = operation_list[i]
            b = bitstring.BitString()
            for r in os:
                b += r.data_in
            op.tdo = b
            
    def openjtag_execute(self, commands):
        pending = deque(commands)

        self.logger.protocol("Running commands %s", commands)
        
        while pending:
            cmd = []
            used = []
            cmd_size = 0
            rsp_size = 0

            while pending and cmd_size < self.port.max_size - 2 and rsp_size < self.port.max_size - 2:
                op = pending.popleft()
                used.append(op)
                c = bytes(op)
                cmd_size += len(c)
                cmd.append(c)
                rsp_size += op.response_size

            cmd_blob = b''.join(cmd)
            self.logger.protocol("OpenJTAG stream: %s rsp %d", cmd_blob.hex(), rsp_size)
            self.port.write(cmd_blob)
            rsp = self.port.read(rsp_size)
            assert len(rsp) == rsp_size

            point = 0
            for c in used:
                data = rsp[point:point+c.response_size]
                c.data_in = c.decode(data)
                point += c.response_size

            assert point == len(rsp)
