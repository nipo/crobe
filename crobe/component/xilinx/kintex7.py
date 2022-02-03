from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from . import series7, xadc

parts = {
    0x0364c093: "160T"
}

@jtag.Chain.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Kintex7(series7.Series7, xadc.Xadc):
    PART_NAMES = {
        "Kintex7-160T": "160T",
    }

    class Efuse0(bitfield.Bitfield):
        all = bitfield.Field(0, 32)

    def __init__(self, port, index, idcode):
        series7.Series7.__init__(self, port, index, idcode)
        self.name = "Kintex7-" + parts[int(self.idcode.drop_revision())]
