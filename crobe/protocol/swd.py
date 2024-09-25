from . import base
from .. import bitstring
from ..db import Db, NoMatch
from ..part_id import PartId
import time
from enum import IntEnum

__all__ = ["Interface", "Ack", "BadTarget", "UnknownDp"]

class Ack(IntEnum):
    OK = 1
    WAIT = 2
    ERROR = 4
    HIGH = 7
    LOW = 0
    INVALID110 = 6
    INVALID101 = 5
    INVALID011 = 3
    PARITY_ERR = 8

class BadSwdio(base.ProtocolError):
    def __init__(self, reason):
        self.__reason = reason
        base.ProtocolError.__init__(self, "SWD Initialization failed")

    def message_get(self):
        return self.__reason

class UnknownDp(base.ProtocolError):
    def message_get(self):
        return "Unknown DP IDR: 0x%08x" % (int(self.args[0]),)

class BadTarget(base.ProtocolError):
    def message_get(self):
        return "Target IDR 0x%08x did not respond" % (int(self.args[0]),)

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

    db = Db("SWD DP IDCODE")
    targetsel_db = Db("SWD Multidrop enumeration DB")
    multidrop_db = Db("SWD Multidrop DP IDCODE")

    IDCODE = 0
    TARGETSEL = 3

    turnaround_supported = True
    # May also be "register" if AP reads are synchronous (delayed read
    # is handled in probe)
    access_method = "raw"

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-SWD")
        self.do_cypress_acquire = False
        self.do_multidrop_enumeration = False
        self.current_target = None
        self.turnaround_cycles = 1

    def line_reset(self):
        if self.do_cypress_acquire:
            return self.cypress_line_reset()

        if self.do_reset:
            self.reset(True)
            time.sleep(.1)
            self.reset(False)
            time.sleep(.1)

        idcode_read = self.cmd_read(False, self.IDCODE)
        ops = [self.cmd_wakeup(), self.cmd_wakeup(),
               self.cmd_wakeup(), self.cmd_wakeup(),
               self.cmd_wakeup(), self.cmd_jtag_to_swd(),
               self.cmd_wakeup(), self.cmd_jtag_to_swd(),
               self.cmd_wakeup(), self.cmd_wakeup(),
               self.cmd_wakeup(), self.cmd_wakeup(),
               self.cmd_run(1),
               idcode_read,
               ]
        self.execute(ops)
        return idcode_read.data

    def cypress_line_reset(self):
        for delay in range(int(self.freq * 1.2e-3),
                           int(self.freq * 5e-3),
                           int(self.freq / 20e3) or 1):
            self.reset(True)
            time.sleep(0.01)
            self.reset(False)
            op = self.cmd_read(False, self.IDCODE)
            ops = [self.cmd_wakeup(delay)] + [
                   op,
                   self.cmd_write(False, 1, 0x54000000),
                   self.cmd_write(False, 2, 0),
                   self.cmd_write(True, 0, 0x00000002), # CSW
                   self.cmd_write(True, 1, 0x40030014), # TAR
                   self.cmd_write(True, 3, 0x80000000), # TEST_MODE
                   ]
            self.execute(ops)
            if op.ack != Ack.OK or ops[-1].ack != Ack.OK:
                continue
            return op.data
        return None

    def option_set(self, opt):
        if opt == "cypress_acquire":
            self.do_cypress_acquire = True
            return
        if opt == "multidrop":
            self.do_multidrop_enumeration = True
            self.turnaround_supported = False
            return
        if opt == "nota":
            self.turnaround_supported = False
            return
        base.Interface.option_set(self, opt)

    def multidrop_enumerate(self):
        # Limit frequency to 1M for line reset and jtag-to-swd.
        with self.freq_capped("enumeration", 1e6):
            self.logger.trace("Multidrop enumeration")

            self.execute([
                self.cmd_wakeup(50),
                self.cmd_swd_to_dormant(),
                self.cmd_wakeup(50),
                self.cmd_dormant_to_swd(),
            ])

            commands = []
            probed = {}
            
            for id, name in self.targetsel_db.registry.items():
                rop = self.cmd_read(0, self.IDCODE)
                commands += [
                    self.cmd_wakeup(50),
                    self.cmd_swd_to_dormant(),
                    self.cmd_wakeup(50),
                    self.cmd_dormant_to_swd(),
                    self.cmd_wakeup(50),
                    self.cmd_run(4),
                    self.cmd_write(0, self.TARGETSEL, int(id)),
                    self.cmd_run(4),
                    rop,
                ]

                probed[id] = rop

            self.execute(commands)

            responses = {}
            for id, rop in probed.items():
                if rop.data in [0, 0xffffffff]:
                    continue
                targetsel = PartId.from_idcode(int(id))
                try:
                    idcode = PartId.from_idcode(rop.data)
                except ValueError:
                    continue

                self.logger.info("Multidrop TargetSel %s gave Idcode %s", targetsel, idcode)
                responses[targetsel] = idcode

            for targetsel, idcode in responses.items():
                self.logger.info("Enumerating TargetSel %s", targetsel)
                try:
                    self.multidrop_probe(targetsel, True)
                except BadTarget as e:
                    self.logger.warning("TargetSel %s was probed as %s but did not answer the second time",
                                        targetsel, idcode)

    def multidrop_probe(self, id, reinit = False):
        with self.freq_capped("multidrop probe", 1e6):
            idcode = self.cmd_read(0, self.IDCODE)
            if reinit:
                self.execute([
                    self.cmd_wakeup(50),
                    self.cmd_swd_to_dormant(),
                    self.cmd_wakeup(50),
                    self.cmd_dormant_to_swd(),
                    self.cmd_wakeup(50),
                    self.cmd_run(4),
                    self.cmd_write(0, self.TARGETSEL, int(id)),
                    self.cmd_run(4),
                    idcode,
                ])
            else:
                self.execute([
                    self.cmd_wakeup(50),
                    self.cmd_run(4),
                    self.cmd_write(0, self.TARGETSEL, int(id)),
                    self.cmd_run(4),
                    idcode,
                ])

            if idcode.data in [0, 0xffffffff]:
                raise BadTarget(id)

            targetid = PartId.from_idcode(int(id))
            try:
                idcode = PartId.from_idcode(idcode.data)
            except ValueError:
                raise BadTarget(id)

            self.logger.info("TargetSel %s Idcode %s",
                             id, idcode)
            target = self.multidrop_db.call(idcode, self, id)
            self.child_add(target)
            self.current_target = None
        
    def start(self):
        super().start()

        if self.do_multidrop_enumeration:
            return self.multidrop_enumerate()
        
        # Limit frequency to 1M for line reset and jtag-to-swd.
        self.freq_cap("enumeration", 1e6)

        partid = None
        for i in range(4):
            idcode = self.line_reset()
            if idcode is None:
                continue
            try:
                partid = PartId.from_idcode(idcode)
            except ValueError:
                continue
            break

        self.freq_cap("enumeration")

        if partid is None:
            raise BadSwdio("Cannot get IDCODE")

        if int(partid) == 0xffffffff:
            raise BadSwdio("SWDIO stuck high")

        if int(partid) == 0:
            raise BadSwdio("SWDIO stuck low")
        
        try:
            self.child_add(self.db.call(partid, self))
        except NoMatch as e:
            raise UnknownDp(partid) from e
        
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

    def wakeup(self, cycles = 50):
        """
        See cmd_wakeup()
        """
        self.execute([self.cmd_wakeup(cycles)])

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

    def cmd_swd_to_dormant(self):
        """
        Returns a SWD-to-Dormant sequence object.
        """
        return SwdToDormant()

    def cmd_dormant_to_swd(self):
        """
        Returns a Dormant-to-SWD sequence object.
        """
        return DormantToSwd()

    def cmd_dormant_to_jtag(self):
        """
        Returns a Dormant-to-JTAG sequence object.
        """
        return DormantToJtag()

    def cmd_dormant_to_jtagserial(self):
        """
        Returns a Dormant-to-JtagSerial sequence object.
        """
        return DormantToJtagSerial()

    def cmd_wakeup(self, cycles = 50):
        """
        Returns a wakeup object. Will cycle SWCLK with SWDIO high for
        at least 50 cycles.
        """
        return Wakeup(cycles)

    def target_select(self, id):
        """
        Select a given multidrop target
        """
        if self.current_target == int(id):
            return
        id_get = self.cmd_read(0, self.IDCODE)
        self.execute([
            self.cmd_wakeup(),
            self.cmd_run(10),
            self.cmd_write(0, self.TARGETSEL, int(id)),
            self.cmd_run(10),
            id_get,
        ])

        self.logger.trace("IDCODE Ack after targetsel %s: %s, %#10x", id, id_get.ack, id_get.data)
        
        if id_get.ack != Ack.OK:
            self.current_target = None
            raise BadTarget(id)

        self.current_target = int(id)
        return PartId.from_idcode(id_get.data)
    
class Operation(base.Operation):
    pass

class Read(Operation):
    def __init__(self, ap, addr):
        self.ap = ap
        self.addr = addr

    @property
    def cmd(self):
        parity = int(self.ap) ^ (self.addr & 1) ^ ((self.addr >> 1) & 1) ^ 1
        return (int(self.ap) << 1) | ((self.addr & 0x3) << 3) | (parity << 5) | 0x85

    # When executed
    data = None
    ack = None

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

    @property
    def cmd(self):
        parity = int(self.ap) ^ (self.addr & 1) ^ ((self.addr >> 1) & 1)
        return (int(self.ap) << 1) | ((self.addr & 0x3) << 3) | (parity << 5) | 0x81

    # When executed
    ack = None
        
    def __str__(self):
        if self.ap:
            return "<Write AP 0x%x 0x%08x>" % (self.addr * 4, self.data)
        else:
            return "<Write DP 0x%x 0x%08x>" % (self.addr, self.data)

class SelectionOperation(Operation):
    out = bitstring.BitString(0, 0)

class JtagToSwd(SelectionOperation):
    def __str__(self):
        return "<JTAG to SWD>"

    out = bitstring.BitString(0b1110011110011110, 16)

class JtagToDormant(SelectionOperation):
    def __str__(self):
        return "<JTAG to Dormant>"

    out = bitstring.BitString(-1, 5) + bitstring.BitString(0x33bbbbba, 32)

class SwdToDormant(SelectionOperation):
    def __str__(self):
        return "<SWD to Dormant>"

    out = bitstring.BitString(-1, 50) + bitstring.BitString(0xe3bc, 16)

class DormantToOther(SelectionOperation):
    def __init__(self, activation_code):
        self.out = bitstring.BitString(-1, 50) \
                   + bitstring.BitString(0x19bc0ea2e3ddafe986852d956209f392, 128) \
                   + bitstring.BitString(0, 4) \
                   + activation_code

class DormantToJtagSerial(DormantToOther):
    def __init__(self):
        super().__init__(bitstring.BitString(0, 12))

    def __str__(self):
        return "<Dormant to JtagSerial>"

class DormantToSwd(DormantToOther):
    def __init__(self):
        super().__init__(bitstring.BitString(0x1a, 8))

    def __str__(self):
        return "<Dormant to Swd>"

class DormantToJtag(DormantToOther):
    def __init__(self):
        super().__init__(bitstring.BitString(0x0a, 8))

    def __str__(self):
        return "<Dormant to Jtag>"

class Wakeup(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Wakeup %d>" % self.cycles

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles
