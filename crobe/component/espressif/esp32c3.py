from ...part_id import PartId
from ...protocol import jtag
from ..riscv import jtag_dtm

@jtag.Chain.db.register(PartId.from_idcode(0x00005c25))
class Esp32c3(jtag.Tap, jtag_dtm.Tap):
    irlen = 5

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode, name = "Esp32c3 Tap")
        jtag_dtm.Tap.__init__(self)

    def start(self):
        jtag.Tap.start(self)
        jtag_dtm.Tap.start(self)
