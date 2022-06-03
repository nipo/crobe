from ...part_id import PartId
from ...protocol import jtag
from ..riscv import jtag_dtm

@jtag.Chain.db.register(PartId.from_idcode(0x0cafe001))
class NeoRv32Tap(jtag.Tap, jtag_dtm.Tap):
    irlen = 5

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode, name = "NeoRV32-Demo")
        jtag_dtm.Tap.__init__(self)

    def start(self):
        jtag.Tap.start(self)
        jtag_dtm.Tap.start(self)
