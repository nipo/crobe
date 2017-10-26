from . import base
from ...model import PortComponent
from ...bitstring import BitString
from ...db import Db, NoMatch
from ...util import pretty
from ...part_id import PartId
import math
import time

__all__ = ["Interface"]

class Interface(base.Interface):
    """
    JTAG protocol interface.

    JTAG protocol model uses 5 basic operations:

    - TAP reset,
    - Capture IR,
    - Capture DR,
    - Data shift (reading TDO or not),
    - Run (with optional cycle count).

    These five operations allow to implement all the operations that
    can be done on a JTAG chain.  Allowed transitions are:

    - Any to TAP Reset,
    - TAP Reset to Capture IR/DR,
    - Capture to Capture (goes through the FSM to capture again),
    - Capture to Shift,
    - Shift to Shift,
    - Capture to Run,
    - Shift to Run,
    - Run to Run.

    Adapter implementations are responsible for handling the FSM as
    they require.  They may take advantage of the Pause IR/DR states
    if they need.

    Basic entry points of the JTAG Interface are either:

    - the synchronous interface:

      * run(),
      * capture_ir(),
      * capture_dr(),
      * shift() (it returns TDO if asked for),
      * tap_reset(),
      * swd_to_jtag();

    - the asynchronous interface, building a list of operation objects
      using operation factories:

      * cmd_run(),
      * cmd_capture_ir(),
      * cmd_capture_dr(),
      * cmd_shift(),
      * cmd_tap_reset(),
      * cmd_swd_to_jtag(),

      then passing the list of operations to execute().  Operations
      will be batched as fast as possible, and execute() will return
      when all operations are flushed.  TDO value will be available on
      each shift operation object where relevant.
    """

    STATE_RESET = "RESET"
    STATE_RTI   = "RTI"
    STATE_SHIFT = "SHIFT"
    STATE_PAUSE = "PAUSE"

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/J")
        self.use_icepick = False

    def start(self):
        chain = Chain(self)
        self.child_add(chain)
        base.Interface.start(self)

    def _execute(self, operation_list):
        raise NotImplementedError()

    def option_set(self, opt):
        if opt == "icepick":
            self.use_icepick = True
            return

        if opt.startswith("freq="):
            self.freq_cap("command line", pretty.sci_parse(opt[5:]))
            return

        base.Interface.option_set(self, opt)
    
    def cmd_shift(self, tdi, read_tdo = True):
        return Shift(tdi, read_tdo)

    def cmd_capture_dr(self):
        return CaptureDr()

    def cmd_capture_ir(self):
        return CaptureIr()

    def cmd_tap_reset(self, count = 5):
        return Reset(count)

    def cmd_swd_to_jtag(self):
        return SwdToJtag()

    def cmd_run(self, count):
        return Run(count)

    def shift(self, tdi, read_tdo = True):
        op = self.cmd_shift(tdi, read_tdo)
        self.execute([op])
        if read_tdo:
            return op.tdo

    def capture_dr(self):
        self.execute([self.cmd_capture_dr()])

    def capture_ir(self):
        self.execute([self.cmd_capture_ir()])

    def tap_reset(self, count = 5):
        self.execute([self.cmd_tap_reset(count)])

    def swd_to_jtag(self):
        self.execute([self.cmd_swd_to_jtag()])

    def run(self, count):
        self.execute([self.cmd_run(count)])

    def __str__(self):
        return "JTAG Interface"
        
class Operation(object):
    def __init__(self):
        pass

    def __repr__(self):
        return str(self)

class CaptureDr(Operation):
    def __str__(self):
        return "<Capture DR>"

class CaptureIr(Operation):
    def __str__(self):
        return "<Capture IR>"

class GenericOperation(Operation):
    def __init__(self):
        pass

class Reset(GenericOperation):
    def __init__(self, count):
        self.tms = BitString(-1, max((count, 5)))

    def __str__(self):
        return "<TAP Reset>"

class SwdToJtag(GenericOperation):
    def __str__(self):
        return "<SWD to JTAG>"

    tms = BitString(-1, 50) + BitString(0xe73c, 16) + BitString(-1, 5)

class Shift(Operation):
    def __init__(self, tdi, read_tdo = True):
        self.tdi = tdi
        self.read_tdo = read_tdo

    # When done, if requested:
    tdo = None

    def __str__(self):
        return "<Shift %s>" % (self.tdi)

class Pause(Operation):
    def __init__(self):
        pass

    def __str__(self):
        return "<Pause>"

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles

class Chain(PortComponent):
    """
    JTAG Chain abstraction, handles discovery of the chain and instanciation of TAPs.

    This can handle SWD to JTAG switching or ICEPick initialization.
    """
    def __init__(self, port):
        PortComponent.__init__(self, port, "JTAG Chain")
        self.name = self.port.port.name + "/C"
        
    def start(self):
        import time

        self.port.freq_cap("enumeration", 1e6)
        
        self.reset()

        if self.port.use_icepick:
            self.icepick_enable()
        else:
            self.swd_to_jtag()
            self.discover()

        self.port.freq_cap("enumeration", None)

        PortComponent.start(self)

    def child_add(self, child):
        PortComponent.child_add(self, child)
        self.port.freq_cap(child, child.max_freq)
        
    def reset(self):
        import time
        self.port.tap_reset()
        self.port.trst = True
        self.port.tap_reset()
        self.port.trst = False
        self.port.tap_reset()
        self.port.run(0)

    def swd_to_jtag(self):
        self.port.swd_to_jtag()
        self.port.tap_reset()
        self.port.run(50)
        
    def icepick_enable(self):
        self.port.freq_cap("icepick", 1e5)
        time.sleep(.001)
        ops = [CaptureIr(), Shift(BitString(-1, 6)), Run(1), CaptureDr()]
        for lengths in [(0, 0, 1), (2, 9)]:
            for l in lengths:
                ops += [Shift(BitString(0, l)), Run(1), CaptureDr(), Pause()]
        ops += [CaptureIr(), Shift(BitString(-1, 16)), Run(0)]
        ops += [Run(5), CaptureIr(), Shift(BitString(0x4, 6)), Run(3)]
        self.port.execute(ops)
        self.port.freq_cap("icepick", None)
        self.discover([PartId(0, 0x17, 0x1ce)])

    def discover(self, forced_idcodes = []):
        """
        This does a blind discovery of the JTAG Chain.  This can
        reliably identify IDCodes of devices that reply their IDCodes
        on TAP reset, and can reliably identify TAP count.

        It does its best to discover TAP IR lengths when possible, in
        a last resort, it will use known TAP idcodes to disambiguify.

        Known components will automatically be instanciated and
        attached on matching TAPs.
        """
        # Get device ID codes
        #self.port.tap_reset()
        self.port.run(1)

        self.port.capture_dr()
        default_dr = BitString()
        dr = True
        while dr:
            dr = self.port.shift(BitString(0, 32))
            default_dr += dr
            dr = int(dr)
            assert len(default_dr) < 500
            
        # Get default IR
        self.port.capture_ir()

        # Clear IR, wait for all zeroes to flow out
        default_ir = BitString()
        ir = True
        while ir:
            ir = self.port.shift(BitString(0, 32))
            default_ir += ir
            ir = int(ir)
            assert len(default_ir) < 500

        # Discover IR length
        ir = self.port.shift(BitString(1, 32))
        while not int(ir):
            ir += self.port.shift(BitString(0, 32))
            assert len(ir) < 500
        total_ir_length = int(math.log(int(ir), 2))

        # Load bypass
        self.port.shift(BitString(-1, total_ir_length), read_tdo = False)

        # Discover device count
        self.port.capture_dr()
        out = self.port.shift(BitString(1, total_ir_length // 2 + 1))
        device_count = int(math.log(int(out), 2))

        if device_count == len(forced_idcodes):
            id_codes = forced_idcodes
        else:
            # Get device ID codes
            id_codes = []
            point = 0
            for i in range(device_count):
                if default_dr[point]:
                    id_codes.append(PartId.from_idcode(int(default_dr[point : point + 32])))
                    point += 32
                else:
                    id_codes.append(None)
                    point += 1

        # Determine possible IR lengths
        ir_length_possibilities = []
        cutoffs = [i for i in range(total_ir_length) if int(default_ir[i : i + 2]) == 1]
        cutoffs.append(total_ir_length)
        def ir_merge(prefix, part, count_left):
            poss = []

            if len(part) < count_left or count_left < 0:
                return []

            if len(part) == count_left:
                return [prefix + part]

            for i in range(1, len(part) + 1):
                poss += ir_merge(prefix + [sum(part[:i])], part[i:], count_left - 1)
            return poss
        ir_length_possibilities = ir_merge([],
                                           [(b-a) for a, b in zip(cutoffs, cutoffs[1:])],
                                           device_count)

        if len(ir_length_possibilities) > 1:
            self.logger.info("Filtering too many possibities %s with known IDCODEs", ir_length_possibilities)

            # Done
            for i, idcode in enumerate(id_codes):
                if not idcode:
                    continue

                irlen = self.irlen_for(idcode)

                if not irlen:
                    continue

                ir_length_possibilities = list(filter(lambda x:x[i] == irlen,
                                                 ir_length_possibilities))
            
        self.logger.info("Found %d devices with IDs %s", len(id_codes), id_codes)
        self.logger.info("IR length possibilities %s", ir_length_possibilities)

        if len(ir_length_possibilities) != 1:
            self.logger.error("Ambiguous IR lengths")
            raise ValueError("Bad IR length possibilities", ir_length_possibilities)

        self.idcodes = id_codes
        self.ir_lengths = ir_length_possibilities[0]

        for index, idcode in enumerate(id_codes):
            tap = Tap.db.call(idcode or PartId.from_idcode(1), self, index)
            self.child_add(tap)

        self.logger.info("Discovered chain:")
        for i, tap in enumerate(self.children):
            self.logger.info("- %s", tap)

    def irlen_for(self, idcode):
        try:
            matches = Tap.db.get(idcode)
        except NoMatch:
            return 0

        if not matches:
            return 0

        possibilities = set()
        for m in matches:
            if m and m.irlen:
                possibilities.add(m.irlen)

        if len(possibilities) != 1:
            return 0

        return possibilities.pop()

    def idcode_at(self, index):
        return self.idcodes[index]

    def ir_pre_post(self, index):
        return sum(self.ir_lengths[:index]), self.ir_lengths[index], sum(self.ir_lengths[index+1:])

    def dr_pre_post(self, index):
        return index, len(self.ir_lengths) - index - 1

    def execute(self, ops):
        self.port.execute(ops)

    def insert(self, index, idcode, irlen = None):
        if isinstance(idcode, int):
            idcode = PartId.from_idcode(idcode)

        if irlen is None:
            irlen = self.irlen_for(idcode)

        for c in self.children[index:]:
            c.index += 1

        self.idcodes.insert(index, idcode)
        self.ir_lengths.insert(index, irlen)

        tap = Tap.db.call(idcode, self, index)
        self.logger.info("Inserting %s at index %d in chain, irlen=%d", idcode, index, irlen)

        self.children.insert(index, tap)

        self.logger.info("New chain:")
        for t in self.children:
            self.logger.info("- %s", t)

        #tap.start()
            
class Tap(PortComponent):
    """
    A TAP model, i.e. a device in a JTAG chain.  This transparently
    handles shifting BYPASS instruction in other TAPs and inserting
    relevant DR shifts through Bypass DR.

    For TAPs that can modify the JTAG chain (like ICE-Pick), there are
    helpers that can insert other TAPs around the current one.

    Like the raw JTAG interface, this object supports both a
    synchronous and an asynchronous interface:

    - object returned by cmd_dr_shift() and cmd_run() can be put in a
      list, batch-executed through a call to execute(),
      
    - dr_shift() and run() allow to do the same, step by step
      (dr_shift returns TDO if asked for).
    """

    """
    Expected IR length of TAP. Can be used by Chain code when
    discovering chain in order to disambiguify discovered chain.
    """
    irlen = None

    """
    TAP Registry, by IDCode.
    """
    db = Db()

    max_freq = None
    
    def __init__(self, port, index):
        PortComponent.__init__(self, port, "TAP[0x%08x]" % int(port.idcode_at(index)))
        self.index = index
        if self.irlen:
            _, irlen, _ = self.ir_pre_post()
            assert irlen == self.irlen
        self.ir = None

    def __str__(self):
        _, irlen, _ = self.ir_pre_post()
        return "%s (TAP#%d, irlen:%d)" % (
            self.name, self.index, irlen)

    def insert_after(self, idcode, irlen = None):
        self.port.insert(self.index + 1, idcode, irlen)

    def insert_before(self, idcode, irlen = None):
        self.port.insert(self.index, idcode, irlen)

    def ir_pre_post(self):
        return self.port.ir_pre_post(self.index)

    def dr_pre_post(self):
        return self.port.dr_pre_post(self.index)
                
    def execute(self, cmds):
        """
        """
        ops = []

        self.logger.debug("running %s", cmds)
        ir_pre, ir_len, ir_post = self.ir_pre_post()
        dr_pre, dr_post = self.dr_pre_post()
        
        for c in cmds:
            if isinstance(c, TapDrShift):
                if self.ir != c.ir or c.read_ir:
                    c.__op = Shift(BitString(c.ir, ir_len), read_tdo = c.read_ir)
                    ops += [CaptureIr(),
                            Shift(BitString(-1, ir_pre)),
                            c.__op,
                            Shift(BitString(-1, ir_post))]
                    self.ir = c.ir

                if c.tdi is not None:
                    ops += [CaptureDr()]
                    if len(c.tdi):
                        c.__op = Shift(c.tdi, read_tdo = c.read_tdo)
                        ops += [Shift(BitString(0, dr_pre)),
                                c.__op,
                                Shift(BitString(0, dr_post))]

            elif isinstance(c, TapRun):
                ops += [Run(c.cycles)]

        self.port.execute(ops)

        for c in cmds:
            if isinstance(c, TapDrShift) and (c.read_tdo or c.read_ir):
                c.tdo = c.postprocess(c.__op.tdo)

    def dr_shift(self, ir, dr, length = None, read_tdo = True, read_ir = False, return_type = None):
        """
        See cmd_dr_shift().
        """
        op = self.cmd_dr_shift(ir, dr, length, read_tdo, read_ir, return_type)
        self.execute([op])
        if read_tdo or dr is not None:
            return op.tdo
        elif read_ir:
            return op.tdo

    def run(self, cycles = 1):
        """
        See cmd_run().
        """
        self.execute([TapRun(cycles)])

    def cmd_dr_shift(self, ir, dr, length = None, read_tdo = True, read_ir = False, return_type = None):
        """
        Shifts DR having a given IR selected. Will only reload IR if needed.

        If read_tdo is True, DR TDO is read back and returned.  If
        read_ir is True, IR is always shifted in and IR captured value is returned.

        dr may be None, in which case only IR is shifted.  Ir read_ir
        is True, dr must be None.

        dr may be either a BitString object (then length must be None)
        or an integer (in which case it will be used as a
        little-endian value of length bits, then length is mandatory).
        """
        return TapDrShift(ir, dr, length, read_tdo, read_ir, return_type)

    def cmd_run(self, cycles):
        """
        Runs the TAP for at least cycles cycles.
        """
        return TapRun(cycles)

Tap.db.register_default(Tap)
    
class TapOperation(object):
    def __str__(self):
        return "<%s>" % self.__class__.__name__

    def __repr__(self):
        return str(self)

class TapDrShift(TapOperation):
    def __init__(self, ir, dr, length = None, read_tdo = True, read_ir = False, return_type = None):
        self.ir = ir
        self.postprocess = return_type or (lambda x:x)
        self.tdo = 0
        self.read_ir = False

        if dr is None and length is None:
            read_tdo = False
            self.read_ir = read_ir
            self.tdi = None
        elif dr is None:
            self.tdi = BitString(0, length)
            self.postprocess = return_type or int
        elif isinstance(dr, BitString):
            self.tdi = dr
        elif isinstance(dr, bytes):
            self.tdi = BitString(dr, length)
        elif isinstance(dr, int):
            assert isinstance(length, int) and length >= 1
            self.tdi = BitString(dr, length)
            self.postprocess = return_type or int
        else:
            raise RuntimeError("Cannot handle dr", dr)

        self.read_tdo = read_tdo

    def __str__(self):
        return "<DrShift 0x%x %s %s>" % (self.ir, self.tdi, BitString(self.tdo, len(self.tdi or [])))
        
class TapRun(TapOperation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<TapRun %d>" % (self.cycles)
