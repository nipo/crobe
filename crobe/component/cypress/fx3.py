from ...part_id import PartId
from ...protocol import jtag

@jtag.Tap.db.register(PartId(0, 0x34, 0x7926))
class FX3(jtag.Tap):
    irlen = 4
    max_freq = 25e6

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "FX3"
