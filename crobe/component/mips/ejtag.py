from ...adapter import jtag
from ...model import Component, PortComponent
from ...part_id import PartId

__all__ = []

class EjtagTap(jtag.Tap):
    irlen = 5

    IDCODE      = 0x1
    IMPCODE     = 0x3
    ADDRESS     = 0x8
    DATA        = 0x9
    CONTROL     = 0xa
    ALL         = 0xb
    EJTAGBOOT   = 0xc
    NORMALBOOT  = 0xd
    FASTDATA    = 0xe
    TCBCONTROLA = 0x10
    TCBCONTROLB = 0x11
    TCBDATA     = 0x12
    TCBCONTROLC = 0x13
    PCSAMPLE    = 0x14

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "EJTAG TAP"

    def start(self):
        self.logger.info("Implementer code: 0x%08x", self.dr_shift(self.IMPCODE, 0, 32))

        jtag.Tap.start(self)
