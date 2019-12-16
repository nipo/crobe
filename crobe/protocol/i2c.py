from . import base
from .. import bitstring
from enum import IntEnum
from ..db import Db, NoMatch

__all__ = ["Interface"]

class ProtocolError(base.ProtocolError):
    pass

class AddressNack(ProtocolError):
    def __init__(self, addr):
        self.__message = addr
        base.ProtocolError.__init__(self, "I2C Slave error", addr)

    def message_get(self):
        return "I2C Address NACK at 0x%02x" % self.args[1]

class DataNack(ProtocolError):
    pass

class Interface(base.Interface):
    """
    I2C protocol interface.
    """

    db = Db("I2C chip type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/I2C")

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
        return op.data

    def write(self, addr, data):
        """
        See cmd_write()
        """
        self.execute([self.cmd_write(addr, data)])

    def write_read(self, addr, data, size):
        """
        See cmd_write() and cmd_read()
        """
        op = self.cmd_read(addr, size)
        self.execute([self.cmd_write(addr, data), op])
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
        try:
            r = self.db.call(sub, self)
            self.child_add(r)
            return r
        except NoMatch:
            return
    
class Operation(object):
    def __repr__(self):
        return str(self)

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
