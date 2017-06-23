import struct
import logging
from enum import Enum

class Component(object):
    """
    Crobe base component.  Everything in crobe is a component
    (Enumerators, Adapters, Interfaces, TAPs, Debug components, SoCs,
    etc.).

    Components are hierarchical, they can have children.

    There are utilities to retrieve a component in the subtree of an
    other.
    """
    def __init__(self, name):
        self.name = name
        self.children = []
        self.__started = False

    def start(self):
        assert not self.__started
        self.__started = True

        self.logger.info("started")
        
        for c in self.children[:]:
            c.start()
        
    def __str__(self):
        return self.__name

    @property
    def started(self):
        return self.__started
    
    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, name):
        self.__name = name
        self.logger = logging.getLogger(name[:10])
    
    def children_find(self, predicate, include_self = False):
        """
        Retrieve childrens in the deep subtree matching predicate.
        """
        ret = []
        if include_self:
            try:
                if predicate(self):
                    ret.append(self)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
        for c in self.children:
            try:
                if predicate(c):
                    ret.append(c)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
            ret += c.children_find(predicate)
        return ret
    
    def children_of_class(self, klass, include_self = False):
        """
        Retrieve childrens in the deep subtree of class klass.
        """
        return self.children_find(lambda x: isinstance(x, klass), include_self)

    def child_add(self, obj):
        self.children.append(obj)
    
class BusComponent(Component):
    """
    Component with a bus interface.
    """

    def __init__(self, name, bus):
        Component.__init__(self, name)
        self.bus = bus

class PortComponent(Component):
    """
    Component with a port interface.
    """

    def __init__(self, name, port):
        Component.__init__(self, name)
        self.port = port

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

    def cmd_u8_write(self, address, data):
        raise NotImplementedError()

    def cmd_u16_write(self, address, data):
        raise NotImplementedError()

    def cmd_u32_write(self, address, data):
        raise NotImplementedError()

class Register(object):
    class Type(Enum):
        GPR = 0
        FLOAT = 1
        PC = 2
        LR = 3
        SP = 4
        SYSTEM = 5

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

    def reset(self, stop = True):
        raise NotImplementedError()

    def reg_write(self, reg, data):
        raise NotImplementedError()

    def reg_read(self, reg):
        raise NotImplementedError()

    def reg_read_all(self):
        raise NotImplementedError()

    def breakpoint_list(self):
        return []

    def breakpoint_add(self, breakpoint):
        raise NotImplementedError()

    def breakpoint_remove(self, breakpoint):
        raise NotImplementedError()

