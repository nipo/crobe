from ...part_id import PartId
from . import ap, dp
from ... import bitfield
from ...bitstring import BitString
from ...adapter.protocol import jtag
import struct

__all__ = ["JtagAp"]

@ap.Ap.db.register(0x14760010)
class JtagAp(ap.Ap):
    CSW               = 0x00
    CSW_SERACTV       = (1 << 31)
    CSW_WFIFOCNT      = lambda x: (x << 28)
    CSW_RFIFOCNT      = lambda x: (x << 24)
    CSW_PORTCONNECTED = (1 << 3)
    CSW_SRSTCONNECTED = (1 << 2)
    CSW_TRST_OUT      = (1 << 1)
    CSW_SRST_OUT      = (1 << 0)
    PORTSEL           = 0x04
    PSTA              = 0x08
    BFIFO0            = 0x10
    BFIFO1            = 0x14
    BFIFO2            = 0x18
    BFIFO3            = 0x1c

    def __init__(self, dp, index = 0):
        ap.Ap.__init__(self, dp, index)
        self.name = "JTAG-AP"

    def start(self):
        ap.Ap.start(self)

        for i in range(8):
            interface = JtagApInterface(self, i)
            print("gni")
            try:
                interface.start()
            except jtag.OpenChain:
                continue
            self.child_add(interface)

class JtagApInterface(jtag.Interface):
    def __init__(self, port, id):
        jtag.Interface.__init__(self, port)
        self.name = "Chain%d" % id
        self.id = id

    def _execute(self, ops):
        for o in ops:
            if isinstance(o, jtag.Shift):
                o.tdo = BitString(-1, len(o.tdi))
