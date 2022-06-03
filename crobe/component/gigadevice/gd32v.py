from ...part_id import PartId
from ...protocol import jtag
from ..riscv import jtag_dtm

@jtag.Chain.db.register(PartId.from_idcode(0x1000563d))
class Gd103vRv32Tap(jtag.Tap, jtag_dtm.Tap):
    irlen = 5

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode, name = "GD32V103 Dbg")
        jtag_dtm.Tap.__init__(self)

    def start(self):
        jtag.Tap.start(self)
        jtag_dtm.Tap.start(self)

@jtag.Chain.db.register(PartId.from_idcode(0x790007A3))
class Gd103vBsTap(jtag.Tap):
    irlen = 5

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode, name = "GD32V103 Bscan")
