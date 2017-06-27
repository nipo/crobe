from . import base
from ... import bitstring
from ...db import Db
from ...part_id import PartId
import time

__all__ = ["Interface"]

class Interface(base.Interface):
    """
    SWD protocol interface.

    SWD protocol model uses 5 basic operations:

    - Line wakeup,
    - JTAG to SWD,
    - Read,
    - Write
    - Run.

    Adapter implementations are responsible for handling the IO as
    they require.  They may insert more idle line cycles between
    operations if needed.

    Basic entry points of the SWD Interface are either:

    - the synchronous interface:

      * read(),
      * write(),
      * run(),
      * wakeup(),
      * jtag_to_swd();

    - the asynchronous interface, building a list of operation objects
      using operation factories:

      * cmd_read(),
      * cmd_write(),
      * cmd_run(),
      * cmd_wakeup(),
      * cmd_jtag_to_swd();

      then passing the list of operations to execute().  Operations
      will be batched as fast as possible, and execute() will return
      when all operations are flushed.  Read value will be available
      on each Read operation object where relevant.
    """

    db = Db()

    IDCODE = 0

    def __init__(self, port):
        base.Interface.__init__(self, "SWD Intf", port)

    def start(self):
        self.port.reset = True
        time.sleep(.005)
        self.port.reset = False
        time.sleep(.050)

        ops = [self.cmd_wakeup(), self.cmd_jtag_to_swd(),
               self.cmd_wakeup(), self.cmd_run(10),
               self.cmd_read(False, self.IDCODE)]
        self.execute(ops)

        partid = PartId.from_idcode(ops[-1].data)

        self.child_add(self.db.call(partid, self))

        base.Interface.start(self)
        
    def _execute(self, operation_list):
        """
        Executes a row of operations.
        """
        raise NotImplementedError()

    def read(self, ap, addr):
        """
        See cmd_read()
        """
        op = self.cmd_read(ap, addr)
        self.execute([op])
        return op.data

    def write(self, ap, addr, data):
        """
        See cmd_write()
        """
        self.execute([self.cmd_write(ap, addr, data)])

    def run(self, cycles):
        """
        See cmd_run()
        """
        self.execute([self.cmd_run(cycles)])

    def jtag_to_swd(self):
        """
        See cmd_jtag_to_swd()
        """
        self.execute([self.cmd_jtag_to_swd()])

    def wakeup(self):
        """
        See cmd_wakeup()
        """
        self.execute([self.cmd_wakeup()])

    def cmd_read(self, ap, addr):
        """
        Returns a read operation object on ap or dp and at given addresss.

        :param int ap: AP (True/1) or DP (False/0)
        :param int addr: Register address (2 bytes, range 0 to 3)

        Property `data` of object will hold a 32-bit value on
        successful execution of operation.
        """
        return Read(ap, addr)

    def cmd_write(self, ap, addr, data):
        """
        Returns a write operation object on ap or dp and at given addresss.

        :param int ap: AP (True/1) or DP (False/0)
        :param int addr: Register address (2 bytes, range 0 to 3)
        :param int data: Value to read
        """
        return Write(ap, addr, data)

    def cmd_run(self, cycles):
        """
        Returns a run operation, will cycle the SWCLK line with SWDIO
        low for a given number of cycles.
        """
        return Run(cycles)

    def cmd_jtag_to_swd(self):
        """
        Returns a JTAG-to-SWD sequence object.
        """
        return JtagToSwd()

    def cmd_wakeup(self):
        """
        Returns a wakeup object. Will cycle SWCLK with SWDIO high for
        at least 50 cycles.
        """
        return Wakeup()
    
class Operation(object):
    def __repr__(self):
        return str(self)

class Read(Operation):
    def __init__(self, ap, addr):
        self.ap = ap
        self.addr = addr

    # When executed
    data = None

    def __str__(self):
        if self.ap:
            return "<Read AP 0x%x>" % (self.addr * 4)
        else:
            return "<Read DP 0x%x>" % (self.addr)
        
class Write(Operation):
    def __init__(self, ap, addr, data):
        self.ap = ap
        self.addr = addr
        self.data = data

    def __str__(self):
        if self.ap:
            return "<Write AP 0x%x 0x%08x>" % (self.addr * 4, self.data)
        else:
            return "<Write DP 0x%x 0x%08x>" % (self.addr, self.data)

class JtagToSwd(Operation):
    def __str__(self):
        return "<JTAG to SWD>"

    out = bitstring.BitString(0b1110011110011110, 16)

class Wakeup(Operation):
    def __str__(self):
        return "<SWD Wakeup>"

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles
