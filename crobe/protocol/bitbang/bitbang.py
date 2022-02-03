from .. import base
from ... import bitstring
from ...db import Db, NoMatch
from ...model import PortComponent
import enum

__all__ = ["ProtocolError", "Mode", "Interface", "Operation", "IoOp", "IoSet", "IoGet", "IoInfo"]

class ProtocolError(base.ProtocolError):
    pass

class Mode(enum.IntFlag):
    Input = 0b00001
    P1    = 0b00010
    P0    = 0b00100
    D1    = 0b01000
    D0    = 0b10000

    D0D1  = Input | D0 | D1
    D0Z1  = Input | D0
    Z0D1  = Input | D1
    D0P1  = Input | D0 | P1
    P0D1  = Input | D1 | P0

class IoInfo:
    supported_modes = 0

class Interface(base.Interface):
    """
    Bitbang protocol interface.
    """

    db = Db("Bitbang user type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-BB")
        
    def _execute(self, operation_list):
        raise NotImplementedError()

    def io_info(self):
        """
        Synchronous informational getter. Returns a dict-like object keyed
        by IO name, values are IoInfo objects.
        """
        return {}

    def set(self, *io_ops):
        """
        See cmd_set()
        """
        op = self.cmd_set(*io_ops)
        self.execute([op])

    def get(self, *ios):
        """
        See cmd_get()
        """
        op = self.cmd_get(ios)
        self.execute([op])
        return [op.values[x] for x in ios]

    def cmd_set(self, *ops):
        return IoSet(*ops)

    def cmd_get(self, ios):
        return IoGet(ios)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

class Operation(base.Operation):
    pass

class IoOp:
    def __init__(self, io, value = None, mode = None):
        self.io = io
        self.value = value
        self.mode = mode

    def __str__(self):
        return "<IoOp %s %s %s>" % (self.io, self.value, self.mode)

class IoSet(Operation):
    def __init__(self, *ops):
        self.ops = ops

    def __str__(self):
        return "<IoSet %s>" % (self.ops)

class IoGet(Operation):
    def __init__(self, ios):
        self.ios = ios
        self.values = {}

    def __str__(self):
        return "<IoGet %s>" % (self.ios)
