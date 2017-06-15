from .model import CoresightComponent

@CoresightComponent.db.register(0x11)
class Tpiu(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base)

        sspsr = self.reg_read(self.SSPSR)
        self.supported_widths = [x+1 for x in range(32) if sspsr & (1 << x)]

    def __str__(self):
        return "Trace Port Interface Unit (supports width %s)" % (",".join(map(str, self.supported_widths)))

    SSPSR = 0x000
    CPSR = 0x004
    ACPR = 0x010
    SPPR = 0x0f0
    STM = 0x100
    TCR = 0x104
    TMR = 0x108
    STPMR = 0x200
    CTPMR = 0x204
    TPRC = 0x208
    FFS = 0x300
    FFC = 0x304
    FSC = 0x308
    EXCTLI = 0x400
    EXCTLO = 0x404
    ITTRFLINACK = 0xee4
    ITTRFLIN = 0xee8
    ITATBDATA0 = 0xeec
    ITATBCTR2 = 0xef0
    ITATBCTR1 = 0xef4
    ITATBCTR0 = 0xef8
