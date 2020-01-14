from ...part_id import PartId
from ...protocol import jtag
from . import series7, xadc

parts = {
    0x03723093: "007",
    0x03722093: "010",
    0x0373c093: "012",
    0x03728093: "014",
    0x0373b093: "015",
    0x03727093: "020",
    0x0372c093: "030",
    0x03732093: "035",
    0x03731093: "045",
    0x03736093: "100",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Zynq(series7.Series7, xadc.Xadc):
    irlen = 6
    max_freq = 66e6
    config_memory_size = 4045564

    def __init__(self, port, index):
        series7.Series7.__init__(self, port, index)
        self.name = "Zynq-" + parts[int(self.idcode.drop_revision())]

    IR_XADC_DRP    = 0x37
