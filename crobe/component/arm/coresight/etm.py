from .model import CoresightComponent
from .. import cpuid

@CoresightComponent.db.register(0x13)
class Etm(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base)
        self.id = self.reg_read(self.ID)
        self.version = "%d.%dr%d" % ((self.id >> 8) & 0xf, (self.id >> 4) & 0xf, self.id & 0xf)

    def __str__(self):
        return "Embedded Trace Macrocell (%s) v%s" % (cpuid.implementer_name(self.id), self.version)

    CR = 0x000
    CCR = 0x004
    TRIGGER = 0x008
    ASICCR = 0x00c
    SR = 0x010
    SCR = 0x014
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
    
    
