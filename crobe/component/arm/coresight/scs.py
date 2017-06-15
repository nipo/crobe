from .model import MemoryMappedComponent
from .. import cpuid
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x000), # m3
    PartId(4, 0x3b, 0x008), # m0
    PartId(4, 0x3b, 0x00c), # m4
    )
class Scs(MemoryMappedComponent):
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base)
        self.reg_write(self.DHCSR, self.DHCSR_KEY | self.DHCSR_DEBUGEN | self.DHCSR_HALT)
        self.reg_write(self.DEMCR, self.reg_read(self.DEMCR) | self.DEMCR_TRCENA)

        self.cpu_name = cpuid.decode(self.cpuid)

        if self.has_fpu:
            self.cpu_name += " with FPU"

        self.name = "System Control Space, " + self.cpu_name

        for i in range(4):
            self.logger.info("PFR%d: 0x%08x", i, self.reg_read(self.ID_PFR(i)))
        for i in range(4):
            self.logger.info("MMFR%d: 0x%08x", i, self.reg_read(self.ID_MMFR(i)))
        for i in range(5):
            self.logger.info("ISAR%d: 0x%08x", i, self.reg_read(self.ID_ISAR(i)))
        for i in range(4):
            self.logger.info("MVFR%d: 0x%08x", i, self.reg_read(self.MVFR(i)))
        
    @property
    def has_fpu(self):
        # Has single or double precision implemented ?
        return bool(self.reg_read(self.MVFR(0)) & 0xff0)

    @property
    def cpuid(self):
        return self.reg_read(self.CPUID)

    # System control and ID registers
    # 0x000-0x00f  Interrupts, Auxilary control
    MCR   = 0x000
    ICTR  = 0x004
    ACTLR = 0x008

    # 0xd00-0xd8f  SCB
    CPUID = 0xd00
    ICSR  = 0xd04
    VTOR  = 0xd08
    AIRCR = 0xd0c
    SCR   = 0xd10
    CCR   = 0xd14
    SHPR1 = 0xd18
    SHPR2 = 0xd1c
    SHPR3 = 0xd20
    SHCSR = 0xd24
    CFSR  = 0xd28
    HFSR  = 0xd2c
    DFSR  = 0xd30
    MMFAR = 0xd34
    BFAR  = 0xd38
    AFSR  = 0xd3c

    # Processor Feature Registers
    ID_PFR = staticmethod(lambda x: 0xd40 + 4 * x)
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
    DHCSR_RESET_ST  = 1 << 25
    DHCSR_RETIRE_ST = 1 << 24
    DHCSR_LOCKUP    = 1 << 19
    DHCSR_SLEEP     = 1 << 18
    DHCSR_HALT      = 1 << 17
    DHCSR_REGRDY    = 1 << 16
    DHCSR_SNAPSTALL = 1 << 5
    DHCSR_MASKINTS  = 1 << 3
    DHCSR_STEP      = 1 << 2
    DHCSR_HALT      = 1 << 1
    DHCSR_DEBUGEN   = 1 << 0


    DCRSR = 0xdf4
    DCRDR = 0xdf8
    DEMCR = 0xdfc
    DEMCR_TRCENA       = 1 << 24
    DEMCR_MON_REQ      = 1 << 19
    DEMCR_MON_STEP     = 1 << 18
    DEMCR_MON_PEND     = 1 << 17
    DEMCR_VC_HARDERR   = 1 << 16
    DEMCR_VC_INTERR    = 1 << 10
    DEMCR_VC_BUSERR    = 1 << 9
    DEMCR_MON_EN       = 1 << 8
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

