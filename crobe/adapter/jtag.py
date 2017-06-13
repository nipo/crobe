from . import model
from ..model import PortComponent
from ..bitstring import BitString
from ..db import Db, NoMatch
from ..part_id import PartId
import math
import time

__all__ = ["CaptureDr", "CaptureIr", "Shift", "Reset", "Run",
           "Chain", "Tap", "TapOperation", "TAP", "CHAIN"]

class Interface(model.Interface):
    STATE_RESET = object()
    STATE_RTI   = object()
    STATE_SHIFT = object()
    STATE_PAUSE = object()

    def __init__(self, port):
        model.Interface.__init__(self, "JTAG Intf", port)

    def execute(self, operation_list):
        raise NotImplementedError()

    def shift(self, tdi, read_tdo = True):
        op = Shift(tdi, read_tdo)
        self.execute([op])
        if read_tdo:
            return op.tdo

    def capture_dr(self):
        self.execute([CaptureDr()])

    def capture_ir(self):
        self.execute([CaptureIr()])

    def reset(self):
        self.execute([Reset()])

    def swd_to_jtag(self):
        self.execute([SwdToJtag()])

    def run(self, count):
        self.execute([Run(count)])

    def chain(self):
        return Chain(self)

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
    def __str__(self):
        return "<TAP Reset>"

    tms = BitString(-1, 5)

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

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles

def version_out(id):
    return PartId(id.jep106_bank, id.jep106_id, id.part_no, 0)

class Chain(PortComponent):
    db = Db(id_filter = version_out)

    def __init__(self, port):
        PortComponent.__init__(self, "JTAG Chain", port)

        self.reset()
        #self.cjtag_enable()
        self.discover()

    def reset(self):
        self.port.reset()
        self.port.swd_to_jtag()
        self.port.reset()
        self.port.run(50)

    def cjtag_enable(self):
        self.port.port.reset = True
        self.port.port.reset = False
        time.sleep(.001)
        self.port.execute([CaptureIr(), Shift(BitString(-1, 64))])
        def do_scan(*lengths):
            ops = []
            for l in lengths:
                ops += [CaptureDr(), Shift(BitString(0, l))]
            ops += [Run(0)]
            self.port.execute(ops)
        do_scan(0, 0, 1)
        do_scan(2, 9)

    def discover(self):
        # Get device ID codes
        #self.port.reset()
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
        device_count = 0
        out = self.port.shift(BitString(1, 32))
        while not out:
            device_count += 32
            out = self.port.shift(BitString(0, 32))
        device_count += int(math.log(int(out), 2))

        # Get device ID codes
        id_codes = []
        point = 0
        for i in range(device_count):
            if default_dr[point]:
                id_codes.append(PartId.from_idcode(int(default_dr[point : point + 32])))
                point += 32
            else:
                id_codes.append(0)
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

        # Done
        for i, idcode in enumerate(id_codes):
            if not idcode:
                continue
            
            try:
                irlen = self.db.call(idcode)
            except NoMatch:
                continue

            ir_length_possibilities = list(filter(lambda x:x[i] == irlen,
                                             ir_length_possibilities))

        self.logger.info("Found %d devices with IDs %s", len(id_codes), id_codes)
        self.logger.info("IR length possibilities %s", ir_length_possibilities)

        if len(ir_length_possibilities) != 1:
            self.logger.error("Ambiguous IR lengths")
            raise ValueError("Bad IR length possibilities", ir_length_possibilities)

        ir_pre = 0
        ir_post = sum(ir_length_possibilities[0])
        dr_pre = 0
        dr_post = len(ir_length_possibilities[0])
        for ir_len, idcode in zip(ir_length_possibilities[0], id_codes):
            ir_post -= ir_len
            dr_post -= 1
            self.children.append(Tap.db.call(idcode, self, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post))
            ir_pre += ir_len
            dr_pre += 1

        for i, tap in enumerate(self.children):
            self.logger.info("Chain TAP #%d: %s", i, tap)
            
    def execute(self, ops):
        self.port.execute(ops)
            
class Tap(PortComponent):
    db = Db(id_filter = version_out)

    def __init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post):
        PortComponent.__init__(self, "TAP[0x%08x]" % int(idcode), port)
        self.ir_pre = ir_pre
        self.ir_len = ir_len
        self.ir_post = ir_post
        self.dr_pre = dr_pre
        self.dr_post = dr_post

    def __str__(self):
        return "%s (IR:%d/%d/%d, DR:%d/-/%d)" % (
            self.name,
            self.ir_pre, self.ir_len, self.ir_post,
            self.dr_pre, self.dr_post)
                
    def execute(self, cmds):
        ops = []
        ir = None

        self.logger.debug("%s running %s", self, cmds)
        
        for c in cmds:
            if isinstance(c, TapDrShift):
                if ir != c.ir:
                    ops += [CaptureIr(),
                            Shift(BitString(-1, self.ir_pre)),
                            Shift(BitString(c.ir, self.ir_len)),
                            Shift(BitString(-1, self.ir_post))]
                    ir = c.ir

                ops += [CaptureDr()]

                if c.tdi is not None:
                    c.__op = Shift(c.tdi, read_tdo = c.read_tdo)
                    ops += [Shift(BitString(0, self.dr_pre)),
                            c.__op,
                            Shift(BitString(0, self.dr_post))]

            elif isinstance(c, TapRun):
                ops += [Run(c.cycles)]

        self.port.execute(ops)

        for c in cmds:
            if isinstance(c, TapDrShift) and c.read_tdo:
                c.tdo = c.postprocess(c.__op.tdo)

    def dr_shift(self, ir, dr, length = None, read_tdo = True):
        op = self.cmd_dr_shift(ir, dr, length, read_tdo)
        self.execute([op])
        if dr is not None and read_tdo:
            return op.tdo

    def run(self, cycles):
        self.execute([TapRun(cycles)])

    def cmd_dr_shift(self, ir, dr, length = None, read_tdo = True):
        return TapDrShift(ir, dr, length, read_tdo)

    def cmd_run(self, cycles):
        return TapRun(cycles)

Tap.db.register_default(Tap)
    
class TapOperation(object):
    def __str__(self):
        return "<%s>" % self.__class__.__name__

class TapDrShift(TapOperation):
    def __init__(self, ir, dr, length = None, read_tdo = True):
        self.ir = ir
        self.postprocess = lambda x:x
        self.tdo = 0

        if dr is None:
            read_tdo = False
            self.tdi = None
        if isinstance(dr, BitString):
            self.tdi = dr
        elif isinstance(dr, int):
            assert isinstance(length, int) and length >= 1
            self.tdi = BitString(dr, length)
            self.postprocess = int
        else:
            raise RuntimeError("Cannot handle dr", dr)

        self.read_tdo = read_tdo

    def __str__(self):
        return "<DrShift 0x%x %s %s>" % (self.ir, self.tdi, BitString(self.tdo, len(self.tdi)))
        
class TapRun(TapOperation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<TapRun %d>" % (self.cycles)
