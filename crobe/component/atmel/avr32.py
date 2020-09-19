from ...protocol import jtag
from ...part_id import PartId

parts = {
    0x1edc: "AVR32",
}

@jtag.Tap.db.register(*[PartId(0, 0x1f, p) for p in parts.keys()])
class Avr32(jtag.Tap):
    irlen = 5

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = parts.get(self.idcode.part_no, "AVR32")
