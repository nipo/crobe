from crobe.component.arm.classic import armv5, debug
from crobe.component.arm.classic.embedded_ice import DebugControl, DebugStatus, Register
import types
import unittest

Mode = armv5.Mode

class FakeCore:
    """
    Debug state ARM core model, at debug operation level.
    """

    def __init__(self, cpsr, pc):
        self.cpsr = cpsr
        self.banks = {bank: {no: (bank << 8) | no for no in bank.banked_registers}
                      for bank in Mode.banks()}
        self.spsr = {bank: 0x1000 | bank for bank in Mode.banks() if bank.has_spsr}
        self.entry_r15 = pc + debug.Debug.PC_ENTRY_OFFSET
        self.memory = bytearray(range(256)) * 16
        self.abort_above = len(self.memory)
        self.pending = None
        self.resumed_at = None
        self.control = 0
        self.cp15 = {}

    @property
    def mode(self):
        return Mode(self.cpsr & 0x1f)

    def reg(self, no):
        if no == 15:
            return self.entry_r15
        return self.banks[self.mode.register_bank(no)][no]

    def reg_set(self, no, value):
        self.banks[self.mode.register_bank(no)][no] = value & 0xffffffff

    def mem_access(self, addr, unit, load, no):
        if addr + unit > self.abort_above:
            self.spsr[Mode.Abt] = self.cpsr
            self.cpsr = (self.cpsr & ~0x1f) | Mode.Abt
            return False
        if load:
            self.reg_set(no, int.from_bytes(self.memory[addr:addr + unit], "little"))
        else:
            self.memory[addr:addr + unit] = (self.reg(no) & ((1 << (8 * unit)) - 1)).to_bytes(unit, "little")
        return True

    def system_speed(self, instr):
        cls = (instr >> 25) & 7
        if cls == 4:
            i = armv5.Ldstm(instr)
            addr = self.reg(i.rn)
            for no in range(16):
                if i.register_list & (1 << no):
                    if not self.mem_access(addr, 4, i.l, no):
                        return
                    addr += 4
        elif cls == 2:
            i = armv5.Ldstr(instr)
            assert i.p == 0
            unit = 1 if i.b else 4
            if self.mem_access(self.reg(i.rn), unit, i.l, i.rd):
                self.reg_set(i.rn, self.reg(i.rn) + i.addr)
        else:
            i = armv5.Ldsth(instr)
            assert cls == 0 and i.c1011 == 0xb and i.p == 0
            if self.mem_access(self.reg(i.rn), 2, i.l, i.rd):
                self.reg_set(i.rn, self.reg(i.rn) + (i.imm_hi << 4 | i.imm_lo))

    def run(self, op):
        if isinstance(op, debug.IceScan):
            if op.addr == Register.DebugStatus:
                op.rdata = int(DebugStatus(dbgack = True, syscomp = True))
            elif op.addr == Register.DebugCtrl:
                if op.wdata is None:
                    op.rdata = self.control
                else:
                    self.control = int(op.wdata)
        elif isinstance(op, debug.WatchPointSetup):
            pass
        elif isinstance(op, debug.RegsRead):
            op.values = {no: self.reg(no) for no in op.nos}
        elif isinstance(op, debug.RegsWrite):
            for no, value in op.values.items():
                self.reg_set(no, value)
        elif isinstance(op, debug.XpsrRead):
            assert not op.spsr or self.mode.has_spsr
            op.value = self.spsr[self.mode.bank] if op.spsr else self.cpsr
            self.reg_set(0, 0xdeadbeef)
        elif isinstance(op, debug.XpsrWrite):
            if op.spsr:
                assert self.mode.has_spsr
                self.spsr[self.mode.bank] = op.value
            else:
                self.cpsr = op.value
        elif isinstance(op, debug.DebugScan):
            if op.sysspeed:
                self.system_speed(self.pending)
            self.pending = op.instr
        elif isinstance(op, debug.Cp15Scan):
            key = (op.op1, op.crn, op.crm, op.op2)
            if op.wdata is None:
                op.rdata = self.cp15.get(key, 0)
                if key == debug.Debug.CP15_DCACHE_TEST_CLEAN:
                    op.rdata = debug.Debug.TEST_CLEAN_DONE
            else:
                self.cp15[key] = op.wdata
            op.complete = True
        elif isinstance(op, debug.ResumeAt):
            self.resumed_at = op.pc
        elif op is not None:
            raise AssertionError(op)

class FakeDebug(debug.Debug):
    def __init__(self, core):
        port = types.SimpleNamespace(
            RESTART = types.SimpleNamespace(cmd = lambda: None),
            cmd_run = lambda count: None,
        )
        super().__init__(port)
        self.core = core

    def execute(self, op_list):
        for op in op_list:
            self.core.run(op)

class DebugTest(unittest.TestCase):
    def setUp(self):
        self.core = FakeCore(0x600000d3, 0x8000)
        self.initial = {bank: dict(regs) for bank, regs in self.core.banks.items()}
        self.dbg = FakeDebug(self.core)

    def test_context_save(self):
        context = self.dbg.context()
        self.assertEqual(context.pc, 0x8000)
        self.assertEqual(context.mode, Mode.Svc)
        self.assertEqual(context.banks, self.initial)
        self.assertEqual(context.spsr, {bank: 0x1000 | bank for bank in Mode.banks() if bank.has_spsr})
        self.assertEqual(self.core.cpsr, 0x600000d3)

    def test_user_mode(self):
        self.core.cpsr = 0x10
        context = self.dbg.context()
        self.assertEqual(context.banks, self.initial)
        self.assertNotIn(Mode.Usr, context.spsr)

    def test_resume_restores(self):
        self.dbg.reg_write(13, 0x1234, Mode.Irq)
        self.dbg.reg_write(9, 0x5678)
        self.dbg.mem_read(0x10, 64)
        self.dbg.resume()
        self.initial[Mode.Irq][13] = 0x1234
        self.initial[Mode.Usr][9] = 0x5678
        self.assertEqual(self.core.banks, self.initial)
        self.assertEqual(self.core.cpsr, 0x600000d3)
        self.assertEqual(self.core.resumed_at, 0x8000)

    def test_mem_read(self):
        for addr, size in [(0, 4), (1, 1), (3, 7), (0x101, 100), (2, 2)]:
            self.assertEqual(self.dbg.mem_read(addr, size), bytes(self.core.memory[addr:addr + size]))

    def test_mem_write(self):
        blob = bytes((x * 7) & 0xff for x in range(83))
        self.dbg.mem_write(0x203, blob)
        self.assertEqual(bytes(self.core.memory[0x203:0x203 + len(blob)]), blob)
        self.assertEqual(self.core.memory[0x202], 2)
        self.assertEqual(self.core.memory[0x203 + len(blob)], (0x203 + len(blob)) & 0xff)
        self.dbg.resume()
        self.assertIn(debug.Debug.CP15_ICACHE_INVALIDATE, self.core.cp15)

    def test_abort(self):
        self.core.abort_above = 0x100
        with self.assertRaises(debug.MemoryAbort):
            self.dbg.mem_read(0xf0, 32)
        self.assertEqual(self.core.cpsr, 0x600000d3)
        self.dbg.resume()
        self.assertEqual(self.core.spsr[Mode.Abt], 0x1000 | Mode.Abt)
        self.assertEqual(self.core.banks, self.initial)

    def test_abort_from_abort_mode(self):
        self.core.cpsr = 0x600000d7
        self.core.abort_above = 0x100
        with self.assertRaises(debug.MemoryAbort):
            self.dbg.mem_write(0xfe, b"abcd")
        self.assertEqual(self.core.cpsr, 0x600000d7)

    def test_thumb_refused(self):
        self.dbg.execute = lambda ops: [setattr(op, "rdata", int(DebugStatus(dbgack = True, itbit = True))) for op in ops]
        with self.assertRaises(NotImplementedError):
            self.dbg.context()

class WatchPointTest(unittest.TestCase):
    def writes(self, **kwargs):
        ret = {}
        tap = types.SimpleNamespace()
        setup = debug.WatchPointSetup(0, **kwargs)
        orig = debug.IceScan.ops
        try:
            debug.IceScan.ops = lambda self, tap: ret.__setitem__(self.addr, self.wdata) or []
            setup.ops(tap)
        finally:
            debug.IceScan.ops = orig
        return ret

    def test_instruction(self):
        w = self.writes(address = 0x100, address_mask = 0xfffffffc, instruction = 0, instruction_mask = 0)
        self.assertEqual(w[Register.Wpt0ControlMask], 0xf7)
        self.assertEqual(w[Register.Wpt0AddrMask], 0x3)
        self.assertEqual(w[Register.Wpt0ControlValue], 0x100)

    def test_data_write(self):
        w = self.writes(address = 0x100, data = 0, data_mask = 0, write = True)
        self.assertEqual(w[Register.Wpt0ControlMask], 0xf6)
        self.assertEqual(w[Register.Wpt0ControlValue], 0x109)
        self.assertEqual(w[Register.Wpt0DataMask], 0xffffffff)

if __name__ == "__main__":
    unittest.main()
