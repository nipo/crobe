from ..model import Cpu, Register
from .coresight.model import MemoryMappedComponent
from .coresight.dwt import Dwt
from .coresight.fpb import Fpb
from .coresight.dbg import Dbg
from .coresight.cti import Cti
from .coresight.scs import Scs
from .coresight.tpiu import Tpiu
from .coresight.etm import Etm
from .coresight.itm import Itm
import time

__all__ = []

class Cortex(Cpu):
    gdb_feature_name = "org.gnu.gdb.arm.m-profile"
    gdb_byteorder = "little"
    cpu_pc_name = "cp"
    cpu_sp_name = "sp"

    def __init__(self, index, scs,
                 fpb = None,
                 dwt = None,
                 tpiu = None,
                 etm = None,
                 itm = None,
                 cti = None):
        Cpu.__init__(self, scs.cpu_name, index)
        self.scs = scs
        self.dwt = dwt
        self.fpb = fpb
        self.tpiu = tpiu
        self.etm = etm
        self.itm = itm
        self.cti = cti
        self.bus = scs.bus

        self.registers = [
            Register(0, "r0", 32, Register.Type.GPR, None),
            Register(1, "r1", 32, Register.Type.GPR, None),
            Register(2, "r2", 32, Register.Type.GPR, None),
            Register(3, "r3", 32, Register.Type.GPR, None),
            Register(4, "r4", 32, Register.Type.GPR, None),
            Register(5, "r5", 32, Register.Type.GPR, None),
            Register(6, "r6", 32, Register.Type.GPR, None),
            Register(7, "r7", 32, Register.Type.GPR, None),
            Register(8, "r8", 32, Register.Type.GPR, None),
            Register(9, "r9", 32, Register.Type.GPR, None),
            Register(10, "r10", 32, Register.Type.GPR, None),
            Register(11, "r11", 32, Register.Type.GPR, None),
            Register(12, "r12", 32, Register.Type.GPR, None),
            Register(13, "sp", 32, Register.Type.SP, None),
            Register(14, "lr", 32, Register.Type.LR, None),
            Register(15, "pc", 32, Register.Type.PC, None),
            Register(16, "xpsr", 32, Register.Type.SYSTEM, None),
            Register(17, "msp", 32, Register.Type.SP, None),
            Register(18, "psp", 32, Register.Type.SP, None),
            Register(20, "cfbp", 32, Register.Type.SYSTEM, None),
            ]

        self.register_by_name = dict([(r.name, r) for r in self.registers])
        self.register_by_number = dict([(r.number, r) for r in self.registers])
        
    def register_get(self, thing):
        if isinstance(thing, Register):
            return thing
        if isinstance(thing, int):
            return self.register_by_number[thing]
        return self.register_by_name[str(thing)]

    @classmethod
    def from_romtable(cls, rt, index, rtindex):
        scs = rt.children_of_class((Scs, Dbg))[rtindex]

        others = {}
        for name, type in [("fpb", Fpb),
                           ("dwt", Dwt),
                           ("cti", Cti),
                           ("tpiu", Tpiu),
                           ("etm", Etm),
                           ("itm", Itm)]:
            try:
                others[name], = rt.children_of_class(type)
            except ValueError:
                pass

        return cls(index, scs = scs, **others)

    def reg_read(self, reg_list):
        return self.scs.cpu_regs_get(reg_list)

    def reg_write(self, reg_value_map):
        return self.scs.cpu_regs_set(reg_value_map)

    @property
    def halt_cause(self):
        return self.scs.cpu_halt_cause
    
    @property
    def state(self):
        return self.scs.cpu_state

    def step(self):
        self.scs.hard_error_catch = True
        self.scs.cpu_step()

    def resume(self, allow_interrupts = False):
        self.scs.hard_error_catch = True
        return self.scs.cpu_resume(allow_interrupts = allow_interrupts)
    
    def halt(self):
        return self.scs.cpu_halt()

    def attach(self):
        self.scs.enable()

        if self.fpb:
            self.fpb.enable()

    def detach(self):
        for b in self.bus.children_of_class(MemoryMappedComponent):
            b.enable(False)

    def reset(self, block_after_reset = True):
        if block_after_reset:
            tmp = self.scs.cpu_reset_catch
            self.scs.cpu_reset_catch = True
            self.scs.cpu_reset()
            time.sleep(.1)
            while self.scs.cpu_state == Cpu.State.RUN:
                pass
            self.scs.cpu_reset_catch = tmp
        else:
            self.scs.cpu_reset()
