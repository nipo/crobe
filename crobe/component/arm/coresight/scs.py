from .model import MemoryMappedComponent
from ...model import Cpu
from .. import cpuid
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x000), # m3
    PartId(4, 0x3b, 0x008), # m0
    PartId(4, 0x3b, 0x00c), # m4
    )
class Scs(MemoryMappedComponent):
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "SCS")
        self.reg_write(self.DHCSR, self.DHCSR_KEY | self.DHCSR_C_MASKINTS | self.DHCSR_C_DEBUGEN | self.DHCSR_C_HALT)
        self.enable()

        self.cpu_name = cpuid.decode(self.cpuid)

        if self.has_fpu:
            self.cpu_name += " with FPU"

        self.name = cpuid.short_name(self.cpuid) + "-SCS"

        self.__cpuid_read()

        self.logger.info("PFR: %s", ', '.join(["0x%08x" % x for x in self.pfr]))
        self.logger.info("DFR: 0x%08x", self.dfr)
        self.logger.info("AFR: 0x%08x", self.afr)
        self.logger.info("MMFR: %s", ', '.join(["0x%08x" % x for x in self.mmfr]))
        self.logger.info("ISAR: %s", ', '.join(["0x%08x" % x for x in self.isar]))
        self.logger.info("MVFR: %s", ', '.join(["0x%08x" % x for x in self.mvfr]))
        self.logger.info("CLIDR: 0x%08x", self.clidr)
        self.logger.info("CCSIDR: 0x%08x", self.ccsidr)

    def __cpuid_read(self):
        cmds = []
        cmds += [self.cmd_reg_read(self.ID_PFR(i)) for i in range(2)]
        cmds += [self.cmd_reg_read(self.ID_DFR)]
        cmds += [self.cmd_reg_read(self.ID_AFR)]
        cmds += [self.cmd_reg_read(self.ID_MMFR(i)) for i in range(4)]
        cmds += [self.cmd_reg_read(self.ID_ISAR(i)) for i in range(5)]
        cmds += [self.cmd_reg_read(self.MVFR(i)) for i in range(3)]
        cmds += [self.cmd_reg_read(self.CLIDR)]
        cmds += [self.cmd_reg_read(self.CCSIDR)]
        self.bus.execute(cmds)

        self.pfr = [op.data for op in cmds[0:2]]
        self.dfr = cmds[2].data
        self.afr = cmds[3].data
        self.mmfr = [op.data for op in cmds[4:8]]
        self.isar = [op.data for op in cmds[8:13]]
        self.mvfr = [op.data for op in cmds[13:16]]
        self.clidr = cmds[16].data
        self.ccsidr = cmds[17].data

    def __str__(self):
        return "System Control Space for %s" % self.cpu_name

    def enable(self, en = True):
        if en:
            self.demcr = self.DEMCR_TRCENA
        else:
            self.cpu_resume()
            self.demcr = 0
            self.reg_write(self.DHCSR, self.DHCSR_KEY)
            self.reg_write(self.DHCSR, 0)
            
    @property
    def has_fpu(self):
        # Has single or double precision implemented ?
        return bool(self.reg_read(self.MVFR(0)) & 0xff0)

    @property
    def cpuid(self):
        return self.reg_read(self.CPUID)

    @property
    def cpu_state(self):
        r = self.reg_read(self.DHCSR)

        if r & self.DHCSR_S_LOCKUP:
            return Cpu.State.LOCKUP

        if r & self.DHCSR_S_SLEEP:
            return Cpu.State.SLEEP

        if r & self.DHCSR_S_HALT:
            return Cpu.State.HALT

        return Cpu.State.RUN

    @property
    def cpu_halt_cause(self):
        r = self.reg_read(self.DFSR)

        if r & self.DFSR_HALTED:
            return Cpu.HaltCause.DEBUGGER

        if r & (self.DFSR_BKPT | self.DFSR_VCATCH):
            return Cpu.HaltCause.BREAKPOINT

        if r & self.DFSR_DWTTRAP:
            return Cpu.HaltCause.WATCHPOINT
        
        return Cpu.HaltCause.UNKNOWN

    def cpu_halt(self):
        self.reg_write(self.DHCSR, self.DHCSR_KEY | self.DHCSR_C_DEBUGEN | self.DHCSR_C_HALT)

        if self.cpu_state == Cpu.State.RUN:
            raise RuntimeError("Unable to halt core")

    def cpu_step(self, allow_interrupts = False):
        maskints = self.DHCSR_C_MASKINTS if not allow_interrupts else 0
        base = self.DHCSR_KEY | self.DHCSR_C_DEBUGEN | maskints
        
        if self.cpu_state == Cpu.State.RUN:
            raise RuntimeError("Cannot single-step a running core")

        self.bus.execute([
            self.cmd_reg_write(self.DFSR, self.DFSR_CLEAR),
            self.cmd_reg_write(self.DHCSR, base | self.DHCSR_C_HALT),
            self.cmd_reg_write(self.DHCSR, base | self.DHCSR_C_STEP),
            ])

    def cpu_resume(self, allow_interrupts = True):
        maskints = self.DHCSR_C_MASKINTS if not allow_interrupts else 0
        base = self.DHCSR_KEY | self.DHCSR_C_DEBUGEN | maskints
        
        self.bus.execute([
            self.cmd_reg_write(self.DFSR, self.DFSR_CLEAR),
            self.cmd_reg_write(self.DHCSR, base | self.DHCSR_C_HALT),
            self.cmd_reg_write(self.DHCSR, base),
            ])

    def cpu_regs_get(self, regs):
        ops = []
        read_ops = []

        for r in regs:
            ro = self.cmd_reg_read(self.DCRDR)

            read_ops.append(ro)
            ops += [
                self.cmd_reg_write(self.DCRSR, r.number, interval = 1e-6),
                ro,
                ]

        self.bus.execute(ops)

        return dict(zip(regs, map(lambda x:x.data, read_ops)))

    def cpu_regs_set(self, regs):
        ops = []

        for r, value in regs.items():
            ops += [
                self.cmd_reg_write(self.DCRDR, value),
                self.cmd_reg_write(self.DCRSR, r.number | self.DCRSR_WRITE, interval = 1e-6),
            ]

        self.bus.execute(ops)

    @property
    def demcr(self):
        return self.reg_read(self.DEMCR)

    @demcr.setter
    def demcr(self, value):
        self.reg_write(self.DEMCR, value)

    @property
    def cpu_reset_catch(self):
        return self.demcr & self.DEMCR_VC_CORERESET

    @cpu_reset_catch.setter
    def cpu_reset_catch(self, value):
        tmp = self.demcr & ~self.DEMCR_VC_CORERESET
        if value:
            tmp |= self.DEMCR_VC_CORERESET
        self.demcr = tmp

    @property
    def hard_error_catch(self):
        return self.demcr & self.DEMCR_VC_HARDERR

    @hard_error_catch.setter
    def hard_error_catch(self, value):
        tmp = self.demcr & ~self.DEMCR_VC_HARDERR
        if value:
            tmp |= self.DEMCR_VC_HARDERR
        self.demcr = tmp

    def cpu_reset(self):
        self.bus.execute([
            self.cmd_reg_write(self.DFSR, self.DFSR_CLEAR),
            self.cmd_reg_write(self.AIRCR, self.AIRCR_KEY | self.AIRCR_SYSRESETREQ),
            ])

        while True:
            dhcsr = self.reg_read(self.DHCSR)
            if not (dhcsr & self.DHCSR_S_RESET_ST):
                break

    # System control and ID registers
    # 0x000-0x00f  Interrupts, Auxilary control
    MCR   = 0x000
    ICTR  = 0x004
    ACTLR = 0x008

    # 0xd00-0xd8f  SCB
    CPUID             = 0xd00
    ICSR              = 0xd04
    VTOR              = 0xd08
    AIRCR             = 0xd0c
    AIRCR_KEY         = 0x05fa0000
    AIRCR_VECTRESET   = 1 << 0
    AIRCR_SYSRESETREQ = 1 << 2
    SCR               = 0xd10
    CCR               = 0xd14
    SHPR1             = 0xd18
    SHPR2             = 0xd1c
    SHPR3             = 0xd20
    SHCSR             = 0xd24
    CFSR              = 0xd28
    HFSR              = 0xd2c
    DFSR              = 0xd30
    DFSR_CLEAR        = 0x1f
    DFSR_HALTED       = 1 << 0
    DFSR_BKPT         = 1 << 1
    DFSR_DWTTRAP      = 1 << 2
    DFSR_VCATCH       = 1 << 3
    DFSR_EXTERNAL     = 1 << 4
    MMFAR             = 0xd34
    BFAR              = 0xd38
    AFSR              = 0xd3c

    # Processor Feature Registers
    ID_PFR = staticmethod(lambda x: 0xd40 + 4 * x)
    ID_DFR = 0xd48
    ID_AFR = 0xd4c
    # Memory Model Feature Registers
    ID_MMFR = staticmethod(lambda x: 0xd50 + 4 * x)
    # Instruction Set Attribute Registers
    ID_ISAR = staticmethod(lambda x: 0xd60 + 4 * x)
    # Instruction Set Attribute Registers
    CLIDR   = 0xd78
    CTR     = 0xd7c
    CCSIDR  = 0xd80
    CSSELR  = 0xd84
    
    CPACR   = 0xd88

    # 0xdf0-0xeff  Debug
    DHCSR = 0xdf0
    DHCSR_KEY = 0xa05f0000
    DHCSR_S_RESET_ST  = 1 << 25
    DHCSR_S_RETIRE_ST = 1 << 24
    DHCSR_S_LOCKUP    = 1 << 19
    DHCSR_S_SLEEP     = 1 << 18
    DHCSR_S_HALT      = 1 << 17
    DHCSR_C_REGRDY    = 1 << 16
    DHCSR_C_SNAPSTALL = 1 << 5
    DHCSR_C_MASKINTS  = 1 << 3
    DHCSR_C_STEP      = 1 << 2
    DHCSR_C_HALT      = 1 << 1
    DHCSR_C_DEBUGEN   = 1 << 0


    DCRSR              = 0xdf4
    DCRSR_WRITE        = 0x10000
    DCRDR              = 0xdf8
    DEMCR              = 0xdfc
    DEMCR_TRCENA       = 1 << 24
    DEMCR_MON_REQ      = 1 << 19
    DEMCR_MON_STEP     = 1 << 18
    DEMCR_MON_PEND     = 1 << 17
    DEMCR_MON_EN       = 1 << 16
    DEMCR_VC_HARDERR   = 1 << 10
    DEMCR_VC_INTERR    = 1 << 9
    DEMCR_VC_BUSERR    = 1 << 8
    DEMCR_VC_STATERR   = 1 << 7
    DEMCR_VC_CHKERR    = 1 << 6
    DEMCR_VC_NOCPERR   = 1 << 5
    DEMCR_VC_MMERR     = 1 << 4
    DEMCR_VC_CORERESET = 1 << 0

    # 0xf00-0xf4f  SWI Trigger
    STIR   = 0xF00

    # SCP / FP Extension
    FPCCR  = 0xf34
    FPCAR  = 0xf38
    FPDSCR = 0xf3c
    # Floating-point feature identification registers
    MVFR   = staticmethod(lambda x: 0xf40 + 4 * x)

    # 0xf50-0xf8f  Cache
    # 0xf90-0xfcf  Implementation defined
    # 0xfd0-0xfff  Microcontroller-specific
    # 0x010-0x0ff SysTick
    STCSR = 0x010
    STRVR = 0x014
    STCVR = 0x018
    STCR  = 0x020
    
    # 0x100-0xcff NVIC
    # 0xd90-0xdef MPU
    MPU_TR = 0xd90
    MPU_CR = 0xd94
    MPU_RNR = 0xd98
    MPU_RBAR = 0xd9c
    MPU_RATR = 0xda0

