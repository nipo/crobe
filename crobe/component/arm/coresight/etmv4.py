from .model import CoresightComponent

#@CoresightComponent.db.register(0x13)
class Etmv4(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base)

    def __str__(self):
        return "Embedded Trace Macrocell v4"

    PRGCTLR    = 0x004
    PROCSELR   = 0x008
    STATR      = 0x00c
    CONFIGR    = 0x010
    AUXCTLR    = 0x018
    EVENTCTL0R = 0x020
    EVENTCTL1R = 0x024
    STALLCTLR  = 0x02c
    TSCTLR     = 0x030
    SYNCPR     = 0x034
    CCCTLR     = 0x038
    BBCTLR     = 0x03c
    TRACEIDR   = 0x040
    QCTLR      = 0x044
    VICTLR     = 0x080
    VIIECTLR   = 0x084
    VISSCTLR   = 0x088
    VIPCSSCTLR = 0x08c
    VDCTLR     = 0x0a0
    VDSACCTLR  = 0x0a4
    VDARCCTLR  = 0x0a8
    SSCSR      = staticmethod(lambda x: 0x2A0 + 4 * x)
    SSPCICR    = staticmethod(lambda x: 0x2C0 + 4 * x)
    OSLAR      = 0x300
    OSLSR      = 0x304
    PDCR       = 0x310
    PDSR       = 0x314
    ACVR       = staticmethod(lambda x: 0x400 + 4 * x)
    ACATR      = staticmethod(lambda x: 0x480 + 4 * x)
    DVCVR      = staticmethod(lambda x: 0x500 + 4 * x)
    DVCMR      = staticmethod(lambda x: 0x580 + 4 * x)
    CIDCVR     = staticmethod(lambda x: 0x600 + 4 * x)
    VMIDCVR    = staticmethod(lambda x: 0x640 + 4 * x)
    CIDCCTLR   = staticmethod(lambda x: 0x680 + 4 * x)
    VMIDCCTLR  = staticmethod(lambda x: 0x688 + 4 * x)
    ITCTRL     = 0xf00
