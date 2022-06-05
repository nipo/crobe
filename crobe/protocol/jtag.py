from . import base
from ..model import PortComponent
from ..bitstring import BitString, BitStringBase
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
        base.Interface.__init__(self, port, name or "ATE")

    def start(self):
        super().start()
        if not self.children:
            self.child_summon("chain")

    def child_spawn(self, sub):
        if sub in ["chain", "0"]:
            return Chain(self)
        
    def _execute(self, operation_list):
        raise NotImplementedError()
    
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
        
    def tap7_control(self, *cps_list):
        with self.freq_capped("cjtag", 1e5):
            def drscan(x):
                if x:
                    return [CaptureDr(), Shift(BitString(-1, x), read_tdo = False)]
                else:
                    return [CaptureDr()]
            reset = [Run(1)]

            ops = reset
            for cps in list(cps_list):
                self.logger.debug("Adding TAP7 init %s", cps)
                for cp in cps:
                    ops += drscan(cp)
            ops += [Run(1)]
            self.execute(ops)

    def cmd_tap7_stmc(self, b, x, y):
        return (0, (b << 2) | (x << 1) | y)

    def cmd_tap7_stc1(self, c, b, v):
        return (1, (c << 4) | (b << 1) | v)

    def cmd_tap7_stc2(self, c, b, v):
        return (2, (c << 4) | (b << 2) | v)

    def cmd_tap7_stfmt(self, n):
        return (3, n)

    def cmd_tap7_mss(self, m):
        return (4, m)

    def cmd_tap7_cce(self, m):
        return (7, m)

    def cmd_tap7_scnb(self, y):
        return (8, y)

    def cmd_tap7_ccl_lock(self):
        return (0, 0, 1)

    def shift_discover(self, max_length = 512, shift_back = False, shift_in = None):
        with self.freq_capped("shift_discover", 1e6):
            marker = 0xc05a5a03
            tdo = self.shift(BitString(marker, 32) + BitString(0, max_length + 4))
            tdo = tdo[:max_length+32]

            if not int(tdo):
                raise OpenChain("TDO stuck low. Bad TDO connection ?")

            if tdo == BitString(-1, len(tdo)):
                raise OpenChain("TDO stuck high. Bad TDO connection ?")

            length = int(math.log(int(tdo), 2) + 1)
            register = tdo[:length - 32]
            rx_marker = tdo[length - 32 : length]

            self.logger.debug("After %d bit shift, tdo = %s, probable length = %d, register = %s, rx_marker = %x (expected %x)", len(tdo), tdo, len(register), register, int(rx_marker), marker)
            if int(tdo[length - 32 : length]) != marker:
                raise OpenChain("TDO changed, but never got TDI back. Bad TDI/TDO connection ?")

            if shift_back:
                self.logger.debug("Shifting back captured value")
                self.shift(register)
            elif shift_in is not None:
                back = BitString(shift_in, len(register))
                self.logger.debug("Shifting back %s", back)
                self.shift(back)
            self.run(1)

            return register
        
    def freq_test(self, fmin, fmax, fstep, ir):
        test = FreqTest(self, fmin, fmax, fstep, ir)
        return test.results()

class Operation(object):
    def __init__(self):
        pass
            
class FreqTest:
    marker = BitString(0x8d09476592d845109b94f6dd0d97d835, 128)

    def __init__(self, interface, fmin = 1e3, fmax = 100e6, fstep = 100, ir = -1):
        self.interface = interface

        self.interface.run(1)
        self.interface.capture_ir()
        self.ir = self.interface.shift_discover(shift_in = ir)

        self.interface.capture_dr()
        self.dr = self.interface.shift_discover(shift_in = 0, max_length = 2048)
        self.interface.run(1)

        self.pad = BitString(0, len(self.dr))

        self.interface.freq_cap("enumeration", None)
        self.interface.freq_cap("shift_discover", None)

        self.tested = set()
        self.freq_fail = set()

        self.__test_step(fmin, fmax, fstep)

        self.interface.freq_cap("test", None)

    def __test_step(self, fmin, fmax, fstep):
        cur = (fmin + fmax) / 2
        effective = self.interface.freq_cap("test", cur)
        if effective in self.tested:
            return
        self.tested.add(effective)

        shift = self.interface.cmd_shift(self.marker + self.pad, read_tdo = True)
        self.interface.execute([self.interface.cmd_capture_dr(), shift, self.interface.cmd_run(1)])
        rb = shift.tdo

        if rb[len(self.pad):] != self.marker:
            self.freq_fail.add(effective)

        if cur - fmin > fstep:
            self.__test_step(fmin, cur, fstep)
        if fmax - cur > fstep:
            self.__test_step(cur, fmax, fstep)

    def results(self):
        last_outcome = None
        group = set()
        for freq in sorted(self.tested):
            outcome = freq not in self.freq_fail
            if outcome != last_outcome:
                if group:
                    yield (min(group), max(group), last_outcome)
                    group = set()
                last_outcome = outcome
            group.add(freq)
        if group:
            yield (min(group), max(group), last_outcome)
            
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

    This can handle SWD to JTAG switching or TAP.7 initialization.
    """

    """
    TAP Registry, by IDCode.
    """
    db = Db("TAP IDCODE")
    
    def __init__(self, port):
        PortComponent.__init__(self, port, "JTAG Chain")
        self.name = "Chain"
        self.default_dr_override = []
        self.tap = {}
        self.total_irlen = 0
        self.total_drlen = 0
        
    def start(self):
        PortComponent.start(self)

        import time

        with self.port.freq_capped("enumeration", 1e6):

            self.reset()

            # Do this first, it will issue TLRs
            self.swd_to_jtag()

            # This is ignored by SWJ-DPs
            self.port.tap7_control(
                self.port.cmd_tap7_ccl_lock(),
                self.port.cmd_tap7_stc2(0, 2, 1),
                self.port.cmd_tap7_stmc(0, 0, 1),
            )

            # Last IR is still IDCODE, so blind discovery should
            # happen nornally even for iCEPicks
            self.discover()

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
        self.execute([
            self.port.cmd_tap_reset(50),
            self.port.cmd_swd_to_jtag(),
            self.port.cmd_tap_reset(50),
            self.port.cmd_run(50),
            ])

    def discover(self):
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
            self.port.cmd_run(50),
            self.port.cmd_capture_dr(),
            ])
        self.logger.trace("Discovering DR after reset")
        reset_dr = self.port.shift_discover()
            
        if len(reset_dr) == 0:
            raise ClosedChain()

        # Get default IR, load bypass
        self.port.capture_ir()
        self.logger.trace("Discovering IR")
        captured_ir = self.port.shift_discover(shift_in = -1)
        captured_ir_length = len(captured_ir)

        # Discover device count
        self.port.capture_dr()
        self.logger.trace("Discovering Bypass DR")
        bypass_dr = self.port.shift_discover(max_length = len(captured_ir) // 2)
        device_count = len(bypass_dr)

        self.logger.note("DR at TAP reset: %s", reset_dr)

        for left, right, idcode in self.default_dr_override:
            reset_dr = reset_dr[:left] + BitString(idcode, 32) + reset_dr[right:]

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

        self.logger.note("IDCodes: %s", id_codes)

                    
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

        
        self.logger.trace("Found %d devices with IDs %s", len(id_codes), id_codes)
        ir_len_filter = [(self.irlen_for(idcode) if idcode is not None else None) for idcode in id_codes]
        self.logger.debug("Known lengths: %s", ir_len_filter)
        ir_length_possibilities = [x
                                   for x in ir_length_possibilities
                                   if all((f is None or f == l) for f, l in zip(ir_len_filter, x))]
            
        self.logger.debug("IR length possibilities %s", ir_length_possibilities)

        if len(ir_length_possibilities) != 1:
            self.logger.error("Ambiguous IR lengths")
            raise ValueError("Bad IR length possibilities", ir_length_possibilities)

        idcodes = [(self.tap.get(index, None) or idcode) for (index, idcode) in enumerate(id_codes)]
        ir_lengths = ir_length_possibilities[0]

        self.taps_set(zip(id_codes, ir_lengths))

    def taps_set(self, id_len):
        for c in self.children:
            self.child_remove(c)

        self.total_irlen = 0
        self.total_drlen = 0

        for idcode, irlen in id_len:
            self.tap_insert(idcode, irlen, self.total_irlen, self.total_drlen)

        self.dump()

    @classmethod
    def irlen_for(cls, idcode):
        try:
            matches = cls.db.get(idcode)
        except NoMatch:
            return None

        if not matches:
            return None

        possibilities = set()
        for m in matches:
            if m and m.irlen:
                possibilities.add(m.irlen)

        if len(possibilities) != 1:
            return None

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
    
    def execute(self, ops):
        self.port.execute(ops)

    def splice(self, ir_pre, irlen, drlen):
        self.logger.trace("Splicing chain at irpre=%d, irlen%+d, drlen%+d",
                          ir_pre, irlen, drlen)
        for t in self.children:
            if t.ir_pre < ir_pre:
                t.position_set(t.ir_pre, t.dr_pre,
                               t.ir_post + irlen, t.dr_post + drlen)
            else:
                t.position_set(t.ir_pre + irlen, t.dr_pre + drlen,
                               t.ir_post, t.dr_post)

        self.total_irlen += irlen
        self.total_drlen += drlen

        for tap in self.children:
            if self.total_irlen != tap.ir_pre + tap.irlen + tap.ir_post:
                self.logger.critical("Bad chain integrity: %s does not match total IRLEN %d", tap, self.total_irlen)
            if self.total_drlen != tap.dr_pre + 1 + tap.dr_post:
                self.logger.critical("Bad chain integrity: %s does not match total DRLEN %d", tap, self.total_drlen)

    def tap_add(self, idcode, irlen, ir_pre, dr_pre):
        self.logger.trace("Adding TAP idcode %s at IR+%d DR+%d, irlen=%s. Current ir=%d, dr=%d",
                          idcode, ir_pre, dr_pre, irlen,
                          self.total_irlen, self.total_drlen)

        tap = self.db.call(idcode, self, idcode)
        if isinstance(tap, Tap):
            if tap.irlen is None:
                tap.irlen = irlen
            taps = [tap]
        elif isinstance(tap, list):
            taps = tap
            assert all(isinstance(tap, Tap) for tap in taps)
        else:
            raise ValueError(tap)

        if any(tap.irlen != irlen for tap in taps):
            raise ValueError(f"Not all returned TAPs for {idcode} have expected irlen")

        for tap in taps:
            self.child_add(tap)
            tap.position_set(ir_pre, dr_pre)

        return taps

    def tap_insert(self, idcode, irlen, ir_pre, dr_pre):
        self.logger.debug("Inserting TAP idcode %s at IR+%d DR+%d, irlen=%s. Current ir=%d, dr=%d",
                          idcode, ir_pre, dr_pre, irlen,
                          self.total_irlen, self.total_drlen)

        if irlen is None:
            irlen = self.irlen_for(idcode)
        self.splice(ir_pre, irlen, 1)
        return self.tap_add(idcode, irlen, ir_pre, dr_pre)

    def dump(self, header = "Current chain"):
        self.logger.info("%s:", header)
        for i, tap in enumerate(self.children):
            self.logger.info("- %s", tap)
    
    def dr_total_len_get(self, irs, max_length = 512):
        ir = BitString()
        for l, v in zip(self.ir_lengths, irs):
            ir += BitString(v, l)
        dr_shift = Shift(BitString(1, max_length), read_tdo = True)
        self.port.execute([
            Run(1),
            CaptureIr(), Shift(ir),
            CaptureDr(), dr_shift,
            CaptureIr(), Shift(BitString(-1, sum(self.ir_lengths))),
            Run(1),
        ])
        total_len = int(math.log(int(dr_shift.tdo), 2))
        return total_len

    def taps_at(self, ir_offset):
        return [
            tap
            for tap in self.children
            if tap.ir_pre <= ir_offset < (tap.ir_pre + tap.irlen)
        ]
        
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
    DEVICE_ID = Dr(32, PartId.from_idcode)
    BYPASS_REG = Dr(1)

    BYPASS = Instruction(-1, "BYPASS_REG")
    
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

    def instructions(self):
        for k, v in self.__dict__.items():
            if isinstance(v, TapInstruction):
                yield v
                
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

    def cmd(self, tdi = None, read_tdo = None, read_ir = False, return_type = None,
            pre_dr_run = 0):
        if return_type is None and self.dr:
            return_type = self.dr.type

        if tdi is None:
            if read_tdo is not None:
                tdi = 0
                if not self.dr or self.dr.length is None:
                    raise ValueError(f"Unknown TDO length for read-only shift")
            else:
                read_tdo = False
        else:
            read_tdo = bool(read_tdo)
            if self.dr and self.dr.length is not None:
                if isinstance(tdi, BitStringBase):
                    if len(tdi) != self.dr.length:
                        raise ValueError(f"Bad TDI length: {len(tdi)}, expected {self.dr.length}")
                else:
                    tdi = int(tdi)

        if tdi is None and not read_tdo:
            length = None
        elif self.dr and self.dr.length:
            length = self.dr.length
        elif isinstance(tdi, BitStringBase):
            length = len(tdi)
        else:
            raise ValueError("Cannot determine shift length")
                    
        return self.tap.cmd_dr_shift(self.ir,
                                     tdi = tdi,
                                     length = length,
                                     read_tdo = read_tdo,
                                     read_ir = read_ir,
                                     return_type = return_type,
                                     pre_dr_run = pre_dr_run)

    def shift(self, *args, **kwargs):
        op = self.cmd(*args, **kwargs)
        self.tap.execute([op])
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
    IR length of TAP. Can be used by Chain code when
    discovering chain in order to disambiguify discovered chain.
    If not set, will be filled by chain enumeration.
    """
    irlen = None

    max_freq = None

    """
    TAP children registry, by usage
    """
    db = Db("TAP subprotocol")

    def __init__(self, port, idcode, name = None):
        if isinstance(idcode, (PartId, int)):
            self.idcode = idcode
        else:
            self.idcode = None
        self.ir_pre = 0
        self.ir_post = 0
        self.dr_pre = 0
        self.dr_post = 0

        if name is None:
            if isinstance(self.idcode, (PartId, int)):
                name = "TAP[0x%08x]" % (int(idcode),)
            else:
                name = "TAP[None]"
        PortComponent.__init__(self, port, name)
        InstructionRegistry.__init__(self)

    def __str__(self):
        return "%s (i=%d/%d/%d, d=%d/%d)" % (
            self.name,
            self.ir_pre, self.irlen or 0, self.ir_post,
            self.dr_pre, self.dr_post)

    def position_set(self, ir_pre, dr_pre, ir_post = None, dr_post = None):
        if ir_post is None:
            ir_post = self.port.total_irlen - ir_pre - self.irlen
        if dr_post is None:
            dr_post = self.port.total_drlen - dr_pre - 1
            
        self.logger.debug("Setting position to i=%d/%d/%d d=%d/%d",
                          ir_pre, self.irlen or 0, ir_post,
                          dr_pre, dr_post)
        self.ir_pre = ir_pre
        self.dr_pre = dr_pre
        self.ir_post = ir_post
        self.dr_post = dr_post
    
    def unchain(self, resize = True):
        chain = self.parent
        chain.child_remove(self)
        chain.splice(self.ir_pre, -self.irlen, -1)

    def insert_after(self, idcode, irlen = None):
        return self.port.tap_insert(idcode, irlen, self.ir_pre + self.irlen, self.dr_pre + 1)

    def insert_before(self, idcode, irlen = None):
        return self.port.tap_insert(idcode, irlen, self.ir_pre, self.dr_pre)
                
    def dr_discover(self, ir, max_length = 512, **kwargs):
        """
        """
        self.dr_shift(ir, None)
        self.port.port.capture_dr()
        max_length += self.dr_pre + self.dr_post
        try:
            register = self.port.port.shift_discover(max_length = max_length,
                                                      **kwargs)
        finally:
            self.dr_shift(-1, None)
        register = register[self.dr_pre : (-self.dr_post) or None]
        self.logger.debug("IR %#x: %d bits, capture value: %s",
                         ir, len(register), register)
        return register

    def dr_discover_all(self, excluded_ir = set()):
        ir_lengths = {}
        for i in range(0, 2 ** self.irlen):
            if i in excluded_ir:
                continue
            try:
                ir_lengths[i] = len(self.dr_discover(i))
            except OpenChain:
                pass
        return ir_lengths
    
    def execute(self, cmds):
        """
        """
        ops = []

        self.logger.protocol("Running %s", cmds)

        current_ir = None

        for c in cmds:
            if isinstance(c, TapDrShift):
                if c.ir:
                    if c.read_ir:
                        c.__op = Shift(BitString(c.ir, self.irlen), read_tdo = True)
                        ops += [
                            CaptureIr(),
                            Shift(BitString(-1, self.ir_pre)),
                            c.__op,
                            Shift(BitString(-1, self.ir_post)),
                        ]
                    elif current_ir != c.ir:
                        ops += [
                            CaptureIr(),
                            Shift(BitString(-1, self.ir_pre)
                                  + BitString(c.ir, self.irlen)
                                  + BitString(-1, self.ir_post), read_tdo = False),
                        ]
                    current_ir = int(c.ir)

                if c.pre_dr_run:
                    ops += [Run(c.pre_dr_run)]

                if c.tdi is not None:
                    ops += [CaptureDr()]
                    if len(c.tdi):
                        c.__op = Shift(c.tdi, read_tdo = c.read_tdo)
                        ops += [Shift(BitString(0, self.dr_pre), read_tdo = False),
                                c.__op,
                                Shift(BitString(0, self.dr_post), read_tdo = False)]

            elif isinstance(c, TapRun):
                ops += [Run(c.cycles)]

#        ops += [Run(1)]

        self.port.execute(ops)

        for c in cmds:
            if isinstance(c, TapDrShift) and (c.read_tdo or c.read_ir):
                c.tdo = c.postprocess(c.__op.tdo)

    def dr_shift(self, *args, **kwargs):
        """
        See cmd_dr_shift().
        """
        op = self.cmd_dr_shift(*args, **kwargs)
        self.execute([op])
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

    # Overridable type for IR status
    IrStatus = int

    def cmd_ir_status(self):
        """
        Shift BYPASS to IR and get back IR status.
        """
        return TapDrShift(-1, None, read_ir = True, return_type = self.IrStatus)

    def cmd_dr_shift(self, *args, **kwargs):
        """
        Shifts DR having a given IR selected. Will only reload IR if needed.

        If read_tdo is True, DR TDO is read back and returned.  If
        read_ir is True, IR is always shifted in and IR captured value is returned.

        tdi may be None, in which case only IR is shifted.  Ir read_ir
        is True, tdi must be None.

        tdi may be either a BitString object (then length must be None)
        or an integer (in which case it will be used as a
        little-endian value of length bits, then length is mandatory).
        """
        return TapDrShift(*args, **kwargs)

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
    def __init__(self, ir, tdi, length = None, read_tdo = True, read_ir = False, return_type = None, pre_dr_run = 0):
        self.ir = int(ir) if ir is not None else None
        self.postprocess = return_type or (lambda x:x)
        self.tdo = 0
        self.read_ir = False
        self.pre_dr_run = pre_dr_run

        if tdi is None and length is None:
            read_tdo = False
            self.read_ir = read_ir
            self.tdi = None
        elif tdi is None:
            self.tdi = BitString(0, length)
            self.postprocess = return_type or int
        elif isinstance(tdi, BitStringBase):
            self.tdi = tdi
        elif isinstance(tdi, bytes):
            self.tdi = BitString(tdi, length)
        elif isinstance(tdi, int):
            assert isinstance(length, int) and length >= 1
            self.tdi = BitString(tdi, length)
            self.postprocess = return_type or int
        else:
            raise RuntimeError("Cannot handle tdi", tdi)

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
