from ...part_id import PartId
from ...adapter import jtag

@jtag.Tap.db.register( PartId(0, 0x41, 0x4001))
class Spartan6(jtag.Tap):
    irlen = 6

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "Spartan-6"
