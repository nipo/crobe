from ...part_id import PartId
from ...protocol import jtag
from . import series7, xadc

parts = {
    0x0362d093: "XC7A35T",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Artix7(series7.Series7, xadc.Xadc):
    irlen = 6
    max_freq = 66e6
    config_memory_size = 4045564

    def __init__(self, port, index):
        series7.Series7.__init__(self, port, index)
        self.name = parts[int(self.idcode.drop_revision())]

    IR_XADC_DRP    = 0x37
