from ...part_id import PartId
from ...adapter.protocol import jtag

@jtag.Tap.db.register(PartId(0, 0x34, 0x7926))
class FX3(jtag.Tap):
    irlen = 4
    max_freq = 10e6

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "FX3"
