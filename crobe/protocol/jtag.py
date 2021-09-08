from . import base
from ..model import PortComponent
from ..bitstring import BitString
from ..db import Db, NoMatch
from ..util import pretty
from ..part_id import PartId
import math
import time
import re

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
        base.Interface.__init__(self, port, (name or port.name) + "-ATE")
        self.use_icepick = False
        self.tap7_tap1_switch = False
        self.child_add(Chain(self))

    def start(self):
        self.logger.info("starting")
        super().start()
        
    def _execute(self, operation_list):
        raise NotImplementedError()

    def option_set(self, opt):
        if opt == "icepick":
            self.use_icepick = True
            self.tap7_tap1_switch = True
            return
        if opt == "tap7":
            self.tap7_tap1_switch = True
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

class Operation(base.Operation):
    pass

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

class OpenChain(base.ProtocolError):
    def __init__(self, message):
        self.__message = message
        base.ProtocolError.__init__(self, "JTAG Initialization failed")

    def message_get(self):
        return self.__message

class ClosedChain(base.ProtocolError):
    def message_get(self):
        return "TDI and TDO are shorted"

class Chain(PortComponent):
    """
    JTAG Chain abstraction, handles discovery of the chain and instanciation of TAPs.

    This can handle SWD to JTAG switching or ICEPick initialization.
    """

    """
    TAP Registry, by IDCode.
    """
    db = Db("TAP IDCODE")

    def __init__(self, port):
        PortComponent.__init__(self, port, "JTAG Chain")
        self.name = self.port.port.name + "-Chain"
        self.default_dr_override = []
        self.tap = {}
        
    def start(self):
        PortComponent.start(self)

        import time

        self.port.freq_cap("enumeration", 1e6)
        
        self.reset()

        if self.port.tap7_tap1_switch:
            self.tap7_tap1_en()
        if self.port.use_icepick:
            self.icepick_enable()
        else:
            self.swd_to_jtag()
            self.port.tap_reset()
            self.discover()

        self.port.freq_cap("enumeration", None)

    def child_add(self, child):
        PortComponent.child_add(self, child)

    def children_changed(self):
        self.port.freq_cap_min(self.children)
        
    def reset(self):
        import time
        cmds = [
            self.port.cmd_tap_reset(),
        ]
        if self.port.do_reset:
            cmds += [
                self.port.cmd_reset(True),
                self.port.cmd_run(50),
                self.port.cmd_reset(False),
            ]
        cmds += [
            self.port.cmd_tap_reset(),
            self.port.cmd_reset(False),
            self.port.cmd_tap_reset(),
            self.port.cmd_run(1),
        ]
        self.execute(cmds)

    def swd_to_jtag(self):
        cmds = [
            self.port.cmd_tap_reset(50),
            self.port.cmd_swd_to_jtag(),
            self.port.cmd_tap_reset(50),
            self.port.cmd_run(50),
            ]
        self.execute(cmds)

    def tap7_cmd(self, lengths_array):
        self.port.freq_cap("tap7", 1e5)
        time.sleep(.001)
        ops = [CaptureIr(), Shift(BitString(-1, 6)), Run(1), CaptureDr()]
        for lengths in [(0, 0, 1)] + lengths_array:
            for l in lengths:
                ops += [Shift(BitString(0, l)), Run(1), CaptureDr()]
        ops += [CaptureIr(), Shift(BitString(-1, 16)), Run(1)]
        self.port.execute(ops)
        self.port.freq_cap("tap7", None)

    def tap7_tap1_en(self):
        self.tap7_cmd([(2, 9)])
        
    def icepick_enable(self):
        self.port.freq_cap("icepick", 1e5)
        time.sleep(.001)
        self.port.execute([Run(5), CaptureIr(), Shift(BitString(0x4, 6)), Run(3)])
        self.port.freq_cap("icepick", None)
        self.discover([PartId(0, 0x17, 0x1ce)])

    def chain_shift_discover(self, max_length = 512, shift_back = False, shift_in = None):
        self.port.freq_cap("shift_discover", 1e6)
        try:
            marker = 0xc05a5a03
            tdo = self.port.shift(BitString(marker, max_length + 36))
            tdo = tdo[:max_length+32]

            if not int(tdo):
                raise OpenChain("TDO stuck low. Bad TDO connection ?")

            if tdo == BitString(-1, len(tdo)):
                raise OpenChain("TDO stuck high. Bad TDO connection ?")

            length = int(math.log(int(tdo), 2) + 1)
            register = tdo[:length - 32]
            rx_marker = tdo[length - 32 : length]

            self.logger.info("After %d bit shift, tdo = %s, probable length = %d, register = %s, rx_marker = %x (expected %x)", len(tdo), tdo, len(register), register, int(rx_marker), marker)
            if int(tdo[length - 32 : length]) != marker:
                raise OpenChain("TDO changed, but never got TDI back. Bad TDI/TDO connection ?")

            if shift_back:
                self.logger.debug("Shifting back captured value")
                self.port.shift(register)
            elif shift_in is not None:
                back = BitString(-1 if bool(shift_in) else 0, len(register))
                self.logger.debug("Shifting back %s", back)
                self.port.shift(back)
            self.port.run(1)

            return register
        finally:
            self.port.freq_cap("shift_discover", None)
            
            
    def discover(self, forced_idcodes = None):
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
        self.port.execute([
#            self.port.cmd_tap_reset(50),
            self.port.cmd_run(50),
            self.port.cmd_capture_dr(),
            ])
        self.logger.debug("Discovering DR after reset")
        reset_dr = self.chain_shift_discover()
            
        if len(reset_dr) == 0:
            raise ClosedChain()

        # Get default IR, load bypass
        self.port.capture_ir()
        self.logger.debug("Discovering IR")
        captured_ir = self.chain_shift_discover(shift_in = 1)
        captured_ir_length = len(captured_ir)

        # Discover device count
        self.port.capture_dr()
        self.logger.debug("Discovering Bypass DR")
        bypass_dr = self.chain_shift_discover(max_length = len(captured_ir) // 2)
        device_count = len(bypass_dr)

        self.logger.info("DR at TAP reset: %s", reset_dr)

        for left, right, idcode in self.default_dr_override:
            reset_dr = reset_dr[:left] + BitString(idcode, 32) + reset_dr[right:]

        if forced_idcodes is not None:
            if len(forced_idcodes) != device_count:
                raise ValueError("Bad forced IDCODE length: %d, expected %d"
                                 % (len(forced_idcodes), device_count))

            id_codes = list(forced_idcodes)
        else:
            # Get device ID codes
            id_codes = []
            point = 0
            for i in range(device_count):
                if reset_dr[point]:
                    id_codes.append(PartId.from_idcode(int(reset_dr[point : point + 32])))
                    point += 32
                else:
                    id_codes.append(None)
                    point += 1

        self.logger.info("IDCodes: %s", id_codes)

                    
        # Determine possible IR lengths
        ir_length_possibilities = []
        cutoffs = [i for i in range(captured_ir_length) if int(captured_ir[i : i + 2]) == 1]
        cutoffs.append(captured_ir_length)
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

        for c in self.children[:]:
            self.child_remove(c)
        
        for index, idcode in enumerate(id_codes):
            try:
                key = self.tap[index]
            except KeyError:
                key = idcode
            tap = Chain.db.call(key, self, index, key)
            self.child_add(tap)
            
        self.logger.info("Discovered chain:")
        for i, tap in enumerate(self.children):
            self.logger.info("- %s", tap)

    def irlen_for(self, idcode):
        try:
            matches = Chain.db.get(idcode)
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

    _default_dr_opt = re.compile(r'default_dr\[(?P<left>\d+):(?P<right>\d+)\]=(?P<idcode>0x[0-9a-fA-F]+)')
    
    def option_set(self, opt):
        m = self._default_dr_opt.match(opt)
        if m:
            self.default_dr_override.append((int(m.group("left")), int(m.group("right")), int(m.group("idcode"), 16)))
            return

        if opt.startswith("tap#"):
            no, value = opt.split("=", 1)
            no = int(no[4:])
            self.tap[no] = value
            return

        super().option_set(opt)
    
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

        tap = Chain.db.call(idcode, self, index)
        self.logger.info("Inserting %s at index %d in chain, irlen=%d", idcode, index, irlen)

        self.children.insert(index, tap)

        self.logger.info("New chain:")
        for t in self.children:
            self.logger.info("- %s", t)

        #tap.start()


        
class Dr:
    def __init__(self, length = None, type = None):
        """
        :param int,None length: Register length, if any (None for infinite/unknown registers)
        :param type type: A type for IO
        """
        self.length = length
        self.type = type

    def _spawn(self, name, tap):
        return TapDr(tap, name, length = self.length, type = self.type)

class Instruction:
    def __init__(self, ir, dr):
        self.ir = ir
        self.dr = dr

    def _spawn(self, name, tap):
        if self.dr is None:
            dr = None
        else:
            try:
                dr = getattr(tap, self.dr)
            except KeyError:
                raise RuntimeError("No such DR: %s" % self.dr)
            if not isinstance(dr, TapDr):
                raise RuntimeError("Not a proper DR: %s" % self.dr)
        return TapInstruction(tap, name, self.ir, dr)

class InstructionRegistry:
    DEVICE_ID = Dr(32)
    TAP_BYPASS = Dr(1)

    BYPASS = Instruction(-1, "TAP_BYPASS")
    
    def __init__(self):
        import inspect

        for name in dir(self):
            obj = inspect.getattr_static(self, name)
            if isinstance(obj, Dr):
                setattr(self, name, obj._spawn(name, self))
                
        for name in dir(self):
            obj = inspect.getattr_static(self, name)
            if isinstance(obj, Instruction):
                setattr(self, name, obj._spawn(name, self))
        
class TapDr:
    def __init__(self, tap, name, length = None, type = int):
        """
        :param Tap tap: Owner TAP
        :param str name: Data register name
        :param int,None length: Register length, if any (None for infinite/unknown registers)
        :param type type: A type for IO
        """
        self.tap = tap
        self.name = name
        self.length = length
        self.type = type

class TapInstruction:
    def __init__(self, tap, name, ir, dr):
        self.tap = tap
        self.name = name
        self.ir = ir
        self.dr = dr

    def cmd(self, dr = None, read_tdo = True, read_ir = False, return_type = None):
        if self.dr is None:
            dr = None
            read_tdo = False
        else:
            if return_type is None:
                return_type = self.dr.type
            if self.dr.type is not None \
               and isinstance(dr, self.dr.type) \
               and self.dr.length is not None:
                dr = int(dr)

            if isinstance(dr, BitString) and self.dr.length is not None:
                if len(dr) != self.dr.length:
                    raise ValueError("Bad DR length", len(dr))
        return self.tap.cmd_dr_shift(self.ir, dr, None if dr is None else self.dr.length,
                                     read_tdo = read_tdo,
                                     read_ir = read_ir,
                                     return_type = return_type)

    def shift(self, dr = None, read_tdo = True, read_ir = False, return_type = None):
        op = self.cmd(dr,
                      read_tdo = read_tdo,
                      read_ir = read_ir,
                      return_type = return_type)
        self.tap.execute([op])
        if read_tdo or dr is not None or read_ir:
            return op.tdo

@Chain.db.register_default
class Tap(PortComponent, InstructionRegistry):
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

    max_freq = None

    """
    TAP children registry, by usage
    """
    db = Db("TAP subprotocol")

    def __init__(self, port, index, idcode, name = None):
        if isinstance(idcode, (PartId, int)):
            self.idcode = idcode
        else:
            self.idcode = None

        if name is None:
            if isinstance(self.idcode, (PartId, int)):
                name = "TAP#%d[0x%08x]" % (index, int(idcode))
            else:
                name = "TAP#%d[None]" % (index,)
        PortComponent.__init__(self, port, name)
        InstructionRegistry.__init__(self)

        self.index = index
        if self.irlen:
            _, irlen, _ = self.ir_pre_post()
            assert irlen == self.irlen
        else:
            _, irlen, _ = self.ir_pre_post()
            self.irlen = irlen
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
                
    def dr_discover(self, ir, max_length = 512, **kwargs):
        """
        """
        dr_pre, dr_post = self.dr_pre_post()
        self.dr_shift(ir, None)
        self.port.port.capture_dr()
        max_length += dr_pre + dr_post
        try:
            register = self.port.chain_shift_discover(max_length = max_length,
                                                      **kwargs)
        finally:
            self.dr_shift(-1, None)
        register = register[dr_pre : (-dr_post) or None]
        self.logger.info("IR %#x: %d bits, capture value: %s",
                         ir, len(register), register)
        return register

    def dr_discover_all(self):
        ir_pre, ir_len, ir_post = self.ir_pre_post()
        ir_lengths = {}
        for i in range(0, 2 ** ir_len):
            try:
                ir_lengths[i] = len(self.dr_discover(i))
            except OpenChain:
                pass
        return ir_lengths
    
    def execute(self, cmds):
        """
        """
        ops = []

        self.logger.debug("running %s", cmds)
        ir_pre, ir_len, ir_post = self.ir_pre_post()
        dr_pre, dr_post = self.dr_pre_post()
        
        for c in cmds:
            if isinstance(c, TapDrShift):
                if c.ir and (self.ir != c.ir or c.read_ir):
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
                        ops += [Shift(BitString(0, dr_pre), read_tdo = False),
                                c.__op,
                                Shift(BitString(0, dr_post), read_tdo = False)]

            elif isinstance(c, TapRun):
                ops += [Run(c.cycles)]

#        ops += [Run(1)]

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

    def ir_status_read(self):
        """
        Shift BYPASS to IR and get back IR status.
        """
        op = self.cmd_ir_status()
        self.execute([op])
        return op.tdo

    def cmd_ir_status(self):
        """
        Shift BYPASS to IR and get back IR status.
        """
        return TapDrShift(-1, None, read_ir = True, return_type = int)

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

    def cmd_run(self, cycles = 1):
        """
        Runs the TAP for at least cycles cycles.
        """
        return TapRun(cycles)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

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
        if self.ir:
            return "<DrShift %s %s %s>" % (self.ir,
                                             self.tdi,
                                             BitString(self.tdo, len(self.tdi or [])))
        else:
            return "<DrShift - %s %s>" % (self.tdi,
                                             BitString(self.tdo, len(self.tdi or [])))
        
class TapRun(TapOperation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<TapRun %d>" % (self.cycles)
