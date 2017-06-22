from ...adapter.protocol import jtag
from ...part_id import PartId

parts = {
    0x1edc: "AVR32",
}

class Avr32(jtag.Tap):
    irlen = 5

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)

@jtag.Tap.db.register(*[PartId(0, 0x1f, p) for p in parts.keys()])
class Avr32Tap(Avr32):
    def __init__(self, port, index):
        Avr32.__init__(self, port, index)
        self.name = parts.get(self.port.idcode_at(index).part_no, "AVR32")
