from .. import base
from ... import bitstring
from ...db import Db, NoMatch
from ...model import PortComponent
import enum

__all__ = ["ProtocolError", "Mode", "Interface", "Operation", "IoInput", "IoPushPull", "IoOpenDrain", "IoSet", "IoGet", "IoInfo"]

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

    def io(self, **crit):
        """
        Retrieve IO definition by some criteria
        """
        raise KeyError(str(crit))

    def set(self, mod_map):
        """
        See cmd_set()
        """
        op = self.cmd_set(mod_map)
        self.execute([op])

    def get(self, io_names):
        """
        See cmd_get()
        """
        op = self.cmd_get(io_names)
        self.execute([op])
        return [op[x] for x in io_names]

    def cmd_set(self, mod_map):
        return IoSet(mod_map)

    def cmd_get(self, io_names):
        return IoGet(io_names)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

class Operation(base.Operation):
    pass

class IoConfig:
    def __init__(self, value = None, mode = None):
        self.value = value
        self.mode = mode

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "<IoConfig %s %s>" % (self.value, self.mode)

class IoInput(IoConfig):
    def __init__(self):
        super().__init__(mode = Mode.Input)

class IoPushPull(IoConfig):
    def __init__(self, value):
        super().__init__(value = value, mode = Mode.D0D1)

class IoOpenDrain(IoConfig):
    def __init__(self, value):
        super().__init__(value = value, mode = Mode.D0Z1)
    
class IoSet(Operation):
    def __init__(self, mod_map):
        self.mod_map = mod_map

    def __str__(self):
        return "<IoSet %s>" % (self.ops,)

class IoGet(Operation):
    def __init__(self, ios):
        self.ios = ios
        self.values = {}

    def __getitem__(self, k):
        return self.values[k]
        
    def __str__(self):
        return "<IoGet %s>" % (self.ios)
