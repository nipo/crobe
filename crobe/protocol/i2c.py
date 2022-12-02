from . import base
from .. import bitstring
from ..component.model import Bus
from enum import IntEnum
from ..db import Db, NoMatch
from ..model import PortComponent

__all__ = ["Interface"]

class ProtocolError(base.ProtocolError):
    pass

class AddressNack(ProtocolError):
    def __init__(self, addr):
        self.__addr = addr
        base.ProtocolError.__init__(self, "I2C Slave error at 0x%02x" % addr)

    def message_get(self):
        return "I2C Address NACK at 0x%02x" % self.__addr

class DataNack(ProtocolError):
    pass

class Interface(base.Interface):
    """
    I2C protocol interface.
    """

    db = Db("I2C chip type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-I2C")

    def start(self):
        self.freq_cap("fast", 400e3)

        base.Interface.start(self)
        
    def _execute(self, operation_list):
        """
        Executes a row of operations, starting with a start condition,
        stopping with a stop condition, with restarts in the middle.
        """
        raise NotImplementedError()

    def read(self, addr, size):
        """
        See cmd_read()
        """
        op = self.cmd_read(addr, size)
        self.execute([op])
        self.logger.protocol("> @%02x %s", addr, op.data.hex())
        return op.data

    def write(self, addr, data):
        """
        See cmd_write()
        """
        self.logger.protocol("< @%02x %s", addr, data.hex())
        self.execute([self.cmd_write(addr, data)])

    def write_read(self, addr, data, size):
        """
        See cmd_write() and cmd_read()
        """
        op = self.cmd_read(addr, size)
        self.logger.protocol("< @%02x %s", addr, data.hex())
        self.execute([self.cmd_write(addr, data), op])
        self.logger.protocol(">     %s", op.data.hex())
        return op.data

    def cmd_read(self, addr, size):
        """
        Returns a read operation object

        :param int addr: Slave address
        :param int size: Read transfer size

        Property `data` of object will hold a byte array value on
        successful execution of operation.
        """
        return Read(addr, size)

    def cmd_write(self, addr, data):
        """
        Returns a write operation object

        :param int addr: Slave address
        :param int data: Value to write
        """
        return Write(addr, data)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

class Slave(PortComponent):
    def __init__(self, port, name, saddr = None):
        PortComponent.__init__(self, port, name)
        self.saddr = saddr

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
            return
        PortComponent.option_set(self, opt)

    def read(self, size):
        op = self.port.cmd_read(self.saddr, size)
        self.port.execute([op])
        return op.data

    def write(self, data):
        self.port.execute([self.port.cmd_write(self.saddr, data)])

    def write_read(self, data, size):
        op = self.port.cmd_read(self.saddr, size)
        self.port.execute([self.port.cmd_write(self.saddr, data), op])
        return op.data

class AddressedSlave(Slave, Bus):
    def __init__(self, bus, name, saddr = None, addr_bytes = 1, page_size = None, saddr_bits = 0):
        Slave.__init__(self, bus, "I2cMem", saddr)
        Bus.__init__(self, self.name)
        self.addr_bytes = addr_bytes
        self.saddr_bits = saddr_bits
        self.size = 1 << (self.addr_bytes * 8 + self.saddr_bits)
        self.page_size = page_size or self.size

    def start(self):
        super().start()
        self.size = 1 << (self.addr_bytes * 8 + self.saddr_bits)
        if self.page_size is None:
            self.page_size = self.size
        
    def _addr(self, addr):
        baddr = (addr & ((1 << (self.addr_bytes * 8)) - 1)).to_bytes(self.addr_bytes, 'big')
        saddr = self.saddr + (addr >> (self.addr_bytes * 8))
        return saddr, baddr

    def read(self, addr, size):
        assert addr + size <= self.size, (addr, size, self.size)

        read_by = min(self.page_size, size, 32)

        cmds = []
        reads = []
        
        r = b''
        for off in range(addr, addr + size, read_by):
            saddr, baddr = self._addr(off)
            saddr_old = self.saddr

            write = self.port.cmd_write(saddr, baddr)
            read = self.port.cmd_read(saddr, read_by)

            cmds += [write, read]
            reads.append(read)
        self.port.execute(cmds)
        return b''.join([op.data for op in reads])

    def write(self, addr, data):
        assert addr + len(data) <= self.size

        cmds = []

        off = 0
        while off < len(data):
            chunk_size = min(len(data) - off, (-(addr + off)) % self.page_size, self.page_size)
            chunk = data[off : off + chunk_size]
            saddr, baddr = self._addr(addr + off)
            write = self.port.cmd_write(saddr, baddr + chunk)
            cmds.append(write)
            off += chunk_size
        self.port.execute(cmds)

    def mem_read(self, address, size):
        return self.read(address, size)

    def mem_write(self, address, data):
        return self.write(address, data)

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr_bits':
            self.saddr_bits = int(v, 16)
            return
        if k == 'addr_bytes':
            self.addr_bytes = int(v)
            return
        if k == 'page_size':
            self.page_size = int(v)
            return
        return super().option_set(opt)

class Operation(base.Operation):
    pass

class Read(Operation):
    def __init__(self, addr, size):
        self.addr = addr
        self.size = size

    # When executed
    data = None

    def __str__(self):
        return "<Read 0x%x, %d bytes>" % (self.addr, self.size)
        
class Write(Operation):
    def __init__(self, addr, data):
        self.addr = addr
        self.data = data
        
    def __str__(self):
        return "<Write 0x%x %s>" % (self.addr, self.data)
