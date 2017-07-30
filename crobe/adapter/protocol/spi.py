from . import base
from ...model import PortComponent
from ... import bitstring
from ...db import Db
from ...part_id import PartId
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

    def __init__(self, port):
        base.Interface.__init__(self, "SPI Intf", port)
        
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

    def shift(self, mosi):
        """
        See cmd_read()
        """
        op = self.cmd_shift(mosi)
        self.execute([op])
        return op.miso

    def cmd_shift(self, mosi):
        """
        Returns a shift operation object.  `miso` is set on shift
        object upon successful execution.

        :param bytes mosi: Value to shift in
        """
        return Shift(mosi)

    def cmd_cs(self, value):
        """
        Toggles CS to value
        """
        return Cs(value)

class Target(PortComponent):

    def transaction(self, mosi):
        op = self.port.cmd_shift(mosi)
        self.port.execute([self.port.cmd_cs(True), op, self.port.cmd_cs(False)])
        return op.miso

class Operation(object):
    def __repr__(self):
        return str(self)

class Shift(Operation):
    def __init__(self, mosi):
        self.mosi = mosi

    # When executed
    miso = None
        
    def __str__(self):
        return "<Shift %s>" % (self.mosi)

class Cs(Operation):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<CS %d>" % self.value
