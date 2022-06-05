from ..model import *
import struct
from enum import Enum
from collections import deque

class MemoryAccessFailure(Exception):
    def __init__(self, address = None):
        self.address = address

    def __str__(self):
        if self.address is not None:
            return f"Memory access failure at {self.address:#010x}"
        return "Memory access failure (imprecise)"

class Bus(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def execute(self, commands):
        raise NotImplementedError()

    def mem_read(self, address, size):
        before = address & 3
        end = address + size
        after = ((end + 3) & ~3) - end

        commands = []
        for a in range(address - before, end + after, 4):
            commands.append(self.cmd_u32_read(a))

        self.execute(commands)

        blob = b"".join([struct.pack("<L", x.data) for x in commands])

        if after:
            return blob[before:-after]
        return blob[before:]

    def mem_write(self, address, data, interval = 0):
        if not data:
            return

        commands = deque()

        if address & 0x1:
            commands.append(self.cmd_u8_write(address, data[0], interval))
            data = data[1:]
            address += 1

        if len(data) >= 2 and address & 0x2:
            commands.append(self.cmd_u16_write(address, struct.unpack("<H", data[:2])[0], interval))
            data = data[2:]
            address += 2

        if len(data) >= 4:
            use = len(data) & ~3
            for o in range(0, use, 4):
                commands.append(self.cmd_u32_write(address + o, struct.unpack("<L", data[o:o+4])[0], interval))
            data = data[use:]
            address += use

        if len(data) >= 2:
            commands.append(self.cmd_u16_write(address, struct.unpack("<H", data[:2])[0], interval))
            data = data[2:]
            address += 2

        if data:
            commands.append(self.cmd_u8_write(address, data[0], interval))

        self.execute(commands)

    def u32_write(self, address, data):
        self.execute([self.cmd_u32_write(address, data)])

    def u32_read(self, address):
        ops = [self.cmd_u32_read(address)]
        self.execute(ops)
        return ops[0].data

    def u16_write(self, address, data):
        self.execute([self.cmd_u16_write(address, data)])

    def u16_read(self, address):
        ops = [self.cmd_u16_read(address)]
        self.execute(ops)
        return ops[0].data

    def u8_write(self, address, data):
        self.execute([self.cmd_u8_write(address, data)])

    def u8_read(self, address):
        ops = [self.cmd_u8_read(address)]
        self.execute(ops)
        return ops[0].data

    def cmd_u8_read(self, address):
        raise NotImplementedError()

    def cmd_u16_read(self, address):
        raise NotImplementedError()

    def cmd_u32_read(self, address):
        raise NotImplementedError()

    def cmd_u8_write(self, address, data, interval = 0):
        raise NotImplementedError()

    def cmd_u16_write(self, address, data, interval = 0):
        raise NotImplementedError()

    def cmd_u32_write(self, address, data, interval = 0):
        raise NotImplementedError()

class Register(object):
    class Type(Enum):
        GPR = 0
        FLOAT = 1
        DOUBLE = 2
        PC = 3
        LR = 4
        SP = 5
        SYSTEM = 6

    def __init__(self, number, name, width, datatype, group):
        self.number = number
        self.name = name
        self.width = width
        self.datatype = datatype
        self.group = group

    def __lt__(self, other):
        return self.number < other.number

    def __lte__(self, other):
        return self.number <= other.number
        
class Cpu(Component):
    class State(Enum):
        RUN     = 0
        HALT    = 1
        SLEEP   = 2
        FAULT   = 3
        LOCKUP  = 4
        UNKNOWN = 5

    class HaltCause(Enum):
        EXCEPTION   = 0
        INSTRUCTION = 1
        BREAKPOINT  = 2
        WATCHPOINT  = 3
        DEBUGGER    = 4
        UNKNOWN     = 5

    def __init__(self, name, core_index):
        Component.__init__(self, name)
        self.core_index = core_index

        # Register number of PC
        self.pc = None
        self.registers = [] # List of Register objects

    @property
    def state(self):
        return self.State.UNKNOWN

    @property
    def halt_cause(self):
        return self.HaltCause.UNKNOWN

    def step(self):
        raise NotImplementedError()

    def resume(self):
        raise NotImplementedError()

    def halt(self):
        raise NotImplementedError()

    def attach(self):
        raise NotImplementedError()

    def detach(self):
        raise NotImplementedError()

    def reset(self, stop = True):
        raise NotImplementedError()

    def reg_write(self, reg_value_map):
        raise NotImplementedError()

    def reg_read(self, reg_list):
        raise NotImplementedError()

    def breakpoint_list(self):
        return []

    def breakpoint_add(self, breakpoint):
        raise NotImplementedError()

    def breakpoint_remove(self, breakpoint):
        raise NotImplementedError()

class _sram_fpga_meta(type):
    def __new__(cls, name, bases, attrs, **kwargs):
        from ..db import Db

        attrs["application_db"] = Db(f"{name} application")

        new_class = type.__new__(cls, name, bases, attrs, **kwargs)
        
        return new_class

class SramFpga(Component, metaclass = _sram_fpga_meta):
    def __init__(self):
        Component.__init__(self)

    def child_spawn(self, sub):
        from ..db import NoMatch

        for clas in self.__class__.__mro__:
            if issubclass(clas, SramFpga):
                self.logger.trace("Looking up %s in application db of %s",
                                  sub, clas)
                try:
                    return clas.application_db.call(sub, self)
                except (NoMatch, BadInvocation):
                    continue
        raise BadInvocation(sub)
        
    def load(self, program):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()

    def reset(self):
        raise NotImplementedError()

class JtagSramFpga(SramFpga):
    def __init__(self):
        SramFpga.__init__(self)

    USER_IR = []
