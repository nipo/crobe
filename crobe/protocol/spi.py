from . import base
from ..model import PortComponent
from .. import bitstring
from ..db import Db, NoMatch
from ..part_id import PartId
import time
from enum import IntEnum

__all__ = ["Interface", "Target"]

class Interface(base.Interface):
    """
    SPI protocol interface.

    SPI protocol model uses 3 basic operations:

    - CS select/deselect,
    - Shift

    Adapter implementations are responsible for handling the IO as
    they require.  They may toggle clock when CS is high if needed.
    """

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/SPI")

    @property
    def reset(self):
        return False

    @reset.setter
    def reset(self, reset):
        raise NotImplementedError("Incapable hardware")

    @property
    def power(self):
        return True

    @power.setter
    def power(self, power):
        raise NotImplementedError("Incapable hardware")
        
    def _execute(self, operation_list):
        """
        Executes a row of operations.
        """
        raise NotImplementedError()

    def cs(self, val):
        """
        See cmd_cs()
        """
        op = self.cmd_cs(val)
        self.execute([op])

    def shift(self, mosi, read_miso = True):
        """
        See cmd_read()
        """
        op = self.cmd_shift(mosi, read_miso)
        self.execute([op])
        return op.miso

    def cmd_shift(self, mosi, read_miso = True):
        """
        Returns a shift operation object.  `miso` is set on shift
        object upon successful execution.

        :param bytes mosi: Value to shift in
        """
        return Shift(mosi, read_miso)

    def cmd_cs(self, value):
        """
        Toggles CS to value
        """
        return Cs(value)
        
class Target(PortComponent, base.FreqCapper):
    db = Db()

    def __init__(self, port, name, cs):
        PortComponent.__init__(self, port, name)
        base.FreqCapper.__init__(self)
        self.cs = cs

    def execute(self, ops):
        self.port.freq_cap("target", self.freq)
        r = self.port.execute(ops)
        self.port.freq_cap("target", None)
        return r

    def transaction(self, mosi, read_miso = True):
        op = self.cmd_shift(mosi, read_miso)
        self.port.execute([self.cmd_cs(True), op, self.cmd_cs(False)])
        if read_miso:
            return op.miso

    def cmd_shift(self, mosi, read_miso = True):
        """
        Returns a shift operation object.  `miso` is set on shift
        object upon successful execution.

        :param bytes mosi: Value to shift in
        """
        return Shift(mosi, read_miso)

    def cmd_cs(self, value):
        """
        Toggles CS to value
        """
        if value:
            return Cs(self.cs)
        return Cs(None)

    def child_spawn(self, sub):
        try:
            return self.db.call(sub, self)
        except NoMatch:
            pass

class Operation(object):
    def __repr__(self):
        return str(self)

class Shift(Operation):
    def __init__(self, mosi, read_miso = True):
        self.mosi = mosi
        self.read_miso = read_miso

    # When executed
    miso = None
        
    def __str__(self):
        return "<Shift %s>" % (self.mosi)

class Cs(Operation):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<CS %d>" % self.value
