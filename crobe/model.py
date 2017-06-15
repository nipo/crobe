import struct
import logging

class Component(object):
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
    
    def children_find(self, predicate):
        ret = list(filter(predicate, self.children))
        for c in self.children:
            ret += c.children_find(predicate)
        return ret

class BusComponent(Component):
    def __init__(self, name, bus):
        Component.__init__(self, name)
        self.bus = bus

class PortComponent(Component):
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
    def __init__(self, number, name, width, datatype, group):
        self.number = number
        self.name = name
        self.width = width
        self.datatype = datatype
        self.group = group

class Cpu(object):
    def __init__(self, name, core_index):
        self.name = name
        self.core_index = core_index

        # Register number of PC
        self.pc = None
        self.registers = [] # List of Register objects

    def step(self):
        raise NotImplementedError()

    def run(self):
        raise NotImplementedError()

    def stop(self):
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

