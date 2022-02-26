from .model import CoresightComponent
from .. import cpuid

@CoresightComponent.db.register(0x13)
class Etm(CoresightComponent):
    def __init__(self, ap, base, name = "ETM"):
        CoresightComponent.__init__(self, ap, base, name)
        self.id = self.reg_read(self.ID)
        self.version = "%d.%dr%d" % (((self.id >> 8) & 0xf) + 1,
                                     (self.id >> 4) & 0xf,
                                     self.id & 0xf)
        self.logger.info("ETM from %s, v%s" % (cpuid.implementer_name(self.id), self.version))
        self.ccr = self.reg_read(self.CCR)
        self.scr = self.reg_read(self.SCR)

        self.logger.note("CPU stall %s, %s",
                         "present" if self.CCR_FIFOFULL_PRESENT(self.ccr) else "absent",
                         "supported" if self.SCR_FIFOFULL_SUPPORTED(self.scr) else "unsupported",
                         )
        self.logger.note("Max port size: %d", self.SCR_MAX_PORT_SIZE(self.scr))

    def __str__(self):
        return "Embedded Trace Macrocell"

    def trace_enable(self, id = None):
        with self.access():
            self.reg_write(self.CR, self.reg_read(self.CR)
                           | self.CR_PROG)

            while not (self.reg_read(self.SR) & self.SR_PROGBIT):
                pass

            self.reg_write(self.CR, 0
                           | self.CR_PROG
                           | self.CR_ENABLE
                           | self.CR_STALL_CPU
                           | self.CR_BRANCH_OUTPUT
                           | self.CR_PORT_SIZE(1)
                           )
            self.reg_write(self.TRACEIDR, id or 0)
            self.reg_write(self.TECR1, 0x1000000)
            self.reg_write(self.FFRR, 0x1000000)
            self.reg_write(self.FFLR, 24)

            self.reg_write(self.CR, self.reg_read(self.CR)
                           & ~self.CR_PROG)

            while self.reg_read(self.SR) & self.SR_PROGBIT:
                pass

            self.logger.note("CR: 0x%08x", self.reg_read(self.CR))
            self.logger.note("SR: 0x%08x", self.reg_read(self.SR))

    CR = 0x000
    CR_PROG          = 1 << 10
    CR_PORT_SIZE     = staticmethod(lambda x: x << 4)
    CR_ENABLE        = 1 << 11
    CR_POWER_DOWN    = 1 << 0
    CR_STALL_CPU     = 1 << 7
    CR_TIMESTAMP     = 1 << 24
    CR_BRANCH_OUTPUT = 1 << 8
    CR_DBG_REQ_CTRL  = 1 << 9
    
    CCR = 0x004
    CCR_PRESENT               = staticmethod(lambda x: (x >> 31) & 1)
    CCR_COPROC                = staticmethod(lambda x: (x >> 27) & 1)
    CCR_START_STOP            = staticmethod(lambda x: (x >> 26) & 1)
    CCR_COMPARATOR_COUNT      = staticmethod(lambda x: (x >> 24) & 3)
    CCR_FIFOFULL_PRESENT      = staticmethod(lambda x: (x >> 23) & 3)
    CCR_EXTERNAL_OUTPUTS      = staticmethod(lambda x: (x >> 20) & 7)
    CCR_EXTERNAL_INPUTS       = staticmethod(lambda x: (x >> 17) & 7)
    CCR_SEQUENCER_PRESENT     = staticmethod(lambda x: (x >> 16) & 1)
    CCR_COUNTER_COUNT         = staticmethod(lambda x: (x >> 13) & 0x7)
    CCR_MM_DECODER_COUNT      = staticmethod(lambda x: (x >> 8) & 0x1f)
    CCR_DATA_COMPARATOR_COUNT = staticmethod(lambda x: (x >> 4) & 0xf)
    CCR_ADDR_COMPARATOR_COUNT = staticmethod(lambda x: (x >> 0) & 0xf)
    
    TRIGGER = 0x008
    ASICCR = 0x00c
    SR = 0x010
    SR_UOF     = 0x00000001
    SR_PROGBIT = 0x00000002
    SR_STATUS  = 0x00000004
    SR_TRIGGER = 0x00000008
    
    SCR = 0x014
    SCR_NO_FETCH_COMPARISONS = staticmethod(lambda x: (x >> 17) & 1)
    SCR_PROCESSOR_COUNT      = staticmethod(lambda x: 1 + ((x >> 12) & 7))
    SCR_PORT_SIZE_SUPPORTED  = staticmethod(lambda x: (x >> 10) & 1)
    SCR_PORT_MODE_SUPPORTED  = staticmethod(lambda x: (x >> 11) & 1)
    SCR_FIFOFULL_SUPPORTED   = staticmethod(lambda x: (x >> 8) & 1)
    SCR_MAX_PORT_SIZE        = staticmethod(lambda x: ((x >> 6) & 0x8) | ((x >> 0) & 0x7))

    TSSCR = 0x018
    TECR2 = 0x01c
    TEEVR = 0x020
    TECR1 = 0x024
    FFRR = 0x028
    FFLR = 0x02c
    VDEVR = 0x030
    VDCR1 = 0x034
    VDCR2 = 0x038
    VDCR3 = 0x03c

    ACVR = staticmethod(lambda x: 0x40 + 4 * x)
    ACTR = staticmethod(lambda x: 0x80 + 4 * x)
    DCVR = staticmethod(lambda x: 0xc0 + 4 * x)
    DCMR = staticmethod(lambda x: 0x100 + 4 * x)
    CNTRLDVR = staticmethod(lambda x: 0x140 + 4 * x)
    CNTENR = staticmethod(lambda x: 0x150 + 4 * x)
    CNTRLDEVR = staticmethod(lambda x: 0x160 + 4 * x)
    CNTVR = staticmethod(lambda x: 0x170 + 4 * x)
    SQabEVR = staticmethod(lambda x: 0x180 + 4 * x)
    SQR = 0x19c
    EXTOUTEVR = staticmethod(lambda x: 0x1a0 + 4 * x)
    CIDCVR = staticmethod(lambda x: 0x1b0 + 4 * x)
    CIDCMR = 0x1bc
    SYNCFR = 0x1e0
    ID = 0x1e4
    CCER = 0x1e8
    EXTINSELR = 0x1ec
    TESSEICR = 0x1f0
    EIBCR = 0x1f4
    TSEVR = 0x1f8
    AUXCR = 0x1fc
    TRACEIDR = 0x200
    IDR2 = 0x208
    VMID = 0x240

    OSLAR = 0x300
    OSLSR = 0x304
    OSSRR = 0x308
    PDCR = 0x310
    PDSR = 0x314
    
    
