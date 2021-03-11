from . import base
from ..model import PortComponent
from ..util.pretty import sci_parse
from .. import bitstring
from ..db import Db, NoMatch
from ..part_id import PartId
import time
from enum import IntEnum
from ..freq_capper import FreqCapper

__all__ = ["Interface", "Target"]

class Interface(base.Interface):
    """
    SPI protocol interface.

    SPI protocol model uses 2 basic operations:

    - CS select/deselect,
    - Shift

    Adapter implementations are responsible for handling the IO as
    they require.  They may toggle clock when CS is high if needed.
    """

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/SPI")

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

    def cs(self, val, mode = 0):
        """
        See cmd_cs()
        """
        op = self.cmd_cs(val, mode)
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

    def cmd_cs(self, value, mode = 0):
        """
        Toggles CS to value
        """
        return Cs(value, mode)

    def option_set(self, opt):
        if opt == "reset=keep":
            self.reset(True)
            return
        super().option_set(opt)

class Target(PortComponent, FreqCapper):
    db = Db("SPI chip type")

    def __init__(self, port, name, cs, mode = 0):
        PortComponent.__init__(self, port, name)
        FreqCapper.__init__(self)
        self.cs = cs
        self.mode = mode
        self.port.freq_cap("target", self.freq)

    def freq_update(self, freq):
        return self.port.freq_cap(self, freq)
        
    def execute(self, ops):
        r = self.port.execute(ops)
        return r

    def transaction(self, mosi, read_miso = True):
        op = self.cmd_shift(mosi, read_miso)
        self.execute([self.cmd_cs(True), op, self.cmd_cs(False)])
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
            return Cs(self.cs, self.mode)
        return Cs(None)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

    def option_set(self, opt):
        if opt.startswith("mode="):
            self.mode = int(opt[5:])
            return
        if opt.startswith("fmax="):
            self.freq_cap("user", sci_parse(opt[5:]))
            return
        super().option_set(opt)

class Operation(base.Operation):
    pass

class Shift(Operation):
    def __init__(self, mosi, read_miso = True):
        self.mosi = mosi if isinstance(mosi, int) else bytes(mosi)
        self.read_miso = read_miso

    # When executed
    miso = None
        
    def __str__(self):
        return "<Shift %s>" % (self.mosi)

class Cs(Operation):
    def __init__(self, value, mode = 0):
        self.value = value
        self.mode = mode

    def __str__(self):
        if self.value is not None:
            return "<CS %d,%d>" % (self.value, self.mode)
        return "<CS None>"
