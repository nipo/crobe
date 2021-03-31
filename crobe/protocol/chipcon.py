from . import base
from ..db import Db
import binascii

__all__ = ["Interface"]

class Interface(base.Interface):
    """
    CC protocol interface, protocol used by 8051-based ChipCon devices
    (now Ti).

    CC protocol model uses 2 basic operations:

    - Debug init,
    - Wait,
    - Command.

    Then there are composed operations, among which are defined memory
    accesses.  Adapter implementor should not care about composed
    operations, as they are transparently decomposed in lower-level
    operations transparently.
    """

    # http://www.ti.com/lit/ug/swra124/swra124.pdf
    # http://www.ti.com/lit/an/swra410/swra410.pdf

    db = Db("CC chip type")


    SFR_CLKCONCMD = 0xc6
    SFR_CLKCONSTA = 0x9e
    SFR_MEMCTR = 0xc7

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-CC")

    def start(self):
        self.freq_cap("enumeration", .5e6)
        self.freq_cap("hardware", 10e6)

        cmds = [
            self.cmd_debug_init(),
            self.cmd_get_chip_id(),
            self.cmd_debug_init(),
            self.cmd_write_config(0x22),
            self.cmd_clk_init(),
            self.cmd_halt(),
            ]
        self.execute(cmds)

#        self.execute([self.cmd_halt()])

        chipid, version = cmds[1].data

        c = self.cmd_read_status()
        c.data = b'\x00'
        while not (c.data[0] & 0x02):
            self.execute([c])
            self.logger.debug("Status: %02x", c.data[0])

        self.child_add(self.db.call(chipid, chipid, self))

        self.freq_cap("enumeration")

        base.Interface.start(self)
        
    def _execute(self, ops):
        """
        Executes a row of operations.
        """
        raise NotImplementedError()

    def execute(self, ops):
        """
        Executes a row of operations, possibly composed.
        """
        steps = []

        for o in ops:
            assert isinstance(o, Operation)
            
            if isinstance(o, ComposedOperation):
                lower = o.decompose(self)
                steps.append(lower)
            else:
                steps.append([o])

        self._execute(sum(steps, []))

        for o, s in zip(ops, steps):
            if isinstance(o, ComposedOperation):
                o.done(s)

    def cmd_sfr_write(self, addr, data):
        assert addr & 0x80
        return self.cmd_data_set(addr, data)

    def cmd_sfr_read(self, addr):
        assert addr & 0x80
        return self.cmd_data_read(addr)

    def cmd_data_write(self, addr, data):
        if not isinstance(data, (list, bytes)):
            data = bytes(data)
        return DataWrite(addr, data)

    def cmd_data_set(self, addr, value):
        # MOV direct, #data
        return self.cmd_debug_instr(bytes([0x75, addr, value]), True)

    def cmd_data_read(self, addr):
        # MOV A, direct
#        return DataRead(addr)
        return self.cmd_debug_instr(bytes([0xe5, addr]), True)

    def cmd_dptr_set(self, addr):
        # MOV DPTR, #data
        return self.cmd_debug_instr(bytes([0x90, addr >> 8, addr & 0xff]), True)

    def cmd_clk_init(self):
        return ClkInit()

    def cmd_debug_init(self):
        """
        Returns a DebugInit operation.
        """
        return DebugInit()

    def command(self, cmd):
        return Command(cmd)

    def cmd_wait(self, cycles):
        return Wait(cycles)

    def cmd_delay(self, sec):
        return self.cmd_wait(int(self.freq * sec))

    def cmd_write_config(self, config):
        return self.command(bytes([Command.WR_CONFIG, config]))

    def cmd_read_config(self):
        return self.command(bytes([Command.RD_CONFIG]))

    def cmd_get_pc(self):
        return self.command(bytes([Command.GET_PC]))

    def cmd_set_pc(self, pc):
        return self.cmd_debug_instr(bytes([0x02, pc >> 8, pc & 0xff]), False)

    STATUS_CHIP_ERASE_DONE = 0x80
    STATUS_PCON_IDLE = 0x40
    STATUS_CPU_HALTED = 0x20
    STATUS_POWER_MODE = 0x10
    STATUS_HALT_BP = 0x08
    STATUS_DEBUG_LOCKED = 0x04
    STATUS_OSCILLATOR_STABLE = 0x02
    STATUS_STACK_OVERFLOW = 0x01

    @property
    def status(self):
        c = self.cmd_read_status()
        self.execute([c])
        return c.data[0]

    @property
    def pc(self):
        c = self.cmd_get_pc()
        self.execute([c])
        return int.from_bytes(c.data, "big")

    @pc.setter
    def pc(self, value):
        self.logger.debug("Setting PC to 0x%04x", value)
        self.execute([self.cmd_set_pc(value)])
        assert self.pc == value

    def resume(self):
        self.logger.debug("Resume state before: %02x", self.status)
        self.execute([self.cmd_resume()])
        self.logger.debug("Resume state after: %02x", self.status)

    def halt(self):
        self.execute([self.cmd_halt()])

    def wait_halted(self):
        status = 0
        while not (status & self.STATUS_CPU_HALTED):
            st = self.status
            if st != status:
                self.logger.debug("Waiting... %02x %04x", st, self.pc)
            status = st

    def cmd_read_status(self):
        return self.command(bytes([Command.READ_STATUS]))

    def cmd_halt(self):
        return self.command(bytes([Command.HALT]))

    def cmd_resume(self):
        return self.command(bytes([Command.RESUME]))

    def cmd_debug_instr(self, instr, read_back):
        assert 1 <= len(instr) <= 3
        read_back = True
        return self.command(bytes([Command.DEBUG_INSTR + (0x04 if read_back else 0) + len(instr)]) + instr)

    def cmd_get_chip_id(self):
        return self.command(bytes([Command.GET_CHIP_ID]))

    def cmd_xreg_write(self, addr, data):
        return self.cmd_xdata_write(addr, bytes([data]))

    def cmd_xreg_read(self, addr):
        return XRegRead(address)

    def cmd_xdata_read(self, address, size):
        return XDataRead(address, size)

    def cmd_xdata_write(self, address, data):
        return XDataWrite(address, data)

    def cmd_dptr_dereference(self):
        # MOVX A, @DPTR
        return self.cmd_debug_instr(bytes([0xe0]), True)

    def cmd_a_set(self, a):
        # MOV A, #imm
        return self.cmd_debug_instr(bytes([0x74, a]), False)

    def cmd_mov_a_rn(self, n):
        # MOV A, rn
        return self.cmd_debug_instr(bytes([0xe8 | n]), True)

    def cmd_mov_rn_a(self, n):
        # MOV rn, A
        return self.cmd_debug_instr(bytes([0xf8 | n]), False)

    def cmd_dptr_a_put(self):
        # MOVX @DPTR, A
        return self.cmd_debug_instr(bytes([0xf0]), True)

    def cmd_dptr_increment(self):
        # INC DPTR
        return self.cmd_debug_instr(bytes([0xa3]), False)

    def cmd_code_read(self, address, size):
        return CodeRead(address, size)

    def cmd_burst_write(self, blob):
        return BurstWrite(blob)

class Operation(object):
    def __repr__(self):
        return str(self)

class DebugInit(Operation):
    def __init__(self):
        pass
        
    def __str__(self):
        return "<DebugInit>"

class Wait(Operation):
    def __init__(self, cycles):
        self.cycles = cycles
        
    def __str__(self):
        return "<Wait %d>" % self.cycles

class BurstWrite(Operation):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return "<BurstWrite %d bytes>" % len(self.data)

class Command(Operation):
    CHIP_ERASE    = 0x14 # 0001 0x00
    WR_CONFIG     = 0x1d # 0001 1x01
    RD_CONFIG     = 0x24 # 0010 0100
    GET_PC        = 0x28 # 0010 1000
    READ_STATUS   = 0x34 # 0011 0x00
    SET_HW_BRKPNT = 0x3b # 0011 1x11
    HALT          = 0x44 # 0100 0100
    RESUME        = 0x4c # 0100 1100
    DEBUG_INSTR   = 0x50 # 0101 0rxx
    STEP_INSTR    = 0x5c # 0101 1100
    STEP_REPLACE  = 0x64 # 0110 01xx
    GET_CHIP_ID   = 0x68 # 0110 1000

    DYN_WAIT = set((x & 0xf8) for x in [
        SET_HW_BRKPNT,
        HALT,
        RESUME,
        DEBUG_INSTR,
        STEP_INSTR,
        STEP_REPLACE,
    ])

    @property
    def should_wait(self):
        return True#(self.command[0] & 0xf8) in self.DYN_WAIT

    def __init__(self, command):
        self.command = command
        if self.command[0] & 0xbb == 0x28:
            self.rlen = 2
        else:
            self.command = bytes([command[0] | 0x04]) + command[1:]
            self.rlen = (self.command[0] >> 2) & 1

    # When executed
    data = None

    def __str__(self):
        return "<Command %s => %d>" % (binascii.b2a_hex(self.command), self.rlen)

class ComposedOperation(Operation):
    def decompose(self, port):
        return []

    def done(self, ops):
        pass

class ClkInit(ComposedOperation):
    def __init__(self):
        pass

    def decompose(self, port):
        return [
            port.cmd_sfr_write(port.SFR_CLKCONCMD, 0x00),
            port.cmd_delay(1e-3),
            ]

    def done(self, ops):
        pass

    def __str__(self):
        return "<ClkInit>"

class XDataRead(ComposedOperation):
    def __init__(self, address, size):
        self.address = address
        self.size = size

    def decompose(self, port):
        ret = [
            port.cmd_dptr_set(self.address),
            ]

        for i in range(self.size):
            ret += [
                port.cmd_dptr_dereference(),
                port.cmd_dptr_increment(),
                ]

        return ret

    def done(self, ops):
        self.data = b''.join(x.data for x in ops[1::2])

    def __str__(self):
        return "<XDataRead 0x%x %d>" % (self.address, self.size)

class XRegRead(ComposedOperation):
    def __init__(self, address):
        self.address = address

    def decompose(self, port):
        return [
            port.cmd_dptr_set(self.address),
            port.cmd_dptr_dereference(),
            ]

    def done(self, ops):
        self.data = ops[1].data[0]

    def __str__(self):
        return "<XRegRead 0x%x>" % (self.address)

class XDataWrite(ComposedOperation):
    def __init__(self, address, data):
        self.address = address
        self.data = data

    def decompose(self, port):
        ret = [
            port.cmd_dptr_set(self.address),
            ]

        for b in self.data:
            ret += [
                port.cmd_a_set(b),
                port.cmd_dptr_a_put(),
                port.cmd_dptr_increment(),
                ]

        return ret

    def __str__(self):
        return "<XDataWrite 0x%x %s>" % (self.address, binascii.b2a_hex(self.data))

class DataWrite(ComposedOperation):
    def __init__(self, address, data):
        self.address = address
        self.data = data

    def decompose(self, port):
        ret = []
        for off, b in enumerate(self.data):
            ret.append(port.cmd_data_set(self.address + off, b))
        return ret

    def __str__(self):
        return "<DataWrite 0x%x %s>" % (self.address, binascii.b2a_hex(self.data))

class CodeRead(ComposedOperation):
    def __init__(self, address, size):
        self.address = address
        self.size = size
        self.indexes = []

    def decompose(self, port):
        init = True
        ret = []
        indexes = []

        for addr in range(self.address, self.address + self.size):
            if addr == self.address or (addr & 0x7fff) == 0:
                ret += [
                    port.cmd_sfr_write(port.SFR_MEMCTR, addr >> 15),
                    port.cmd_dptr_set((addr & 0x7fff) | 0x8000),
                    ]

            indexes.append(len(ret))
            ret += [
                port.cmd_dptr_dereference(),
                port.cmd_dptr_increment(),
                ]

        self.indexes = indexes

        return ret

    def done(self, ops):
        self.data = b''.join(ops[i].data for i in self.indexes)

    def __str__(self):
        return "<CodeRead 0x%x %d>" % (self.address, self.size)

class DataRead(ComposedOperation):
    def __init__(self, address):
        self.address = address

    def decompose(self, port):
        return [
            port.cmd_debug_instr(bytes([0xe5, self.address]), True),
            ]

    def done(self, ops):
        self.data = ops[2].data

    def __str__(self):
        return "<DataRead 0x%x>" % (self.address)

class Ping(ComposedOperation):
    def __init__(self, data):
        self.wdata = data

    def decompose(self, port):
        return [
            port.cmd_a_set(self.wdata),
            port.cmd_mov_rn_a(0),
            port.cmd_mov_a_rn(0),
            ]

    def done(self, ops):
        self.data = ops[2].data

    def __str__(self):
        return "<Ping 0x%x>" % (self.wdata)
