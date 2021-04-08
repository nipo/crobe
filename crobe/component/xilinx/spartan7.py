from ...part_id import PartId
from ...protocol import jtag
from ...db import Db
from . import series7, xadc

parts = {
    0x03622093: "S6",
    0x03620093: "S15",
    0x037c4093: "S25",
    0x0362f093: "S50",
    0x037c8093: "S75",
    0x037c7093: "S100",
}

@jtag.Chain.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Spartan7(series7.Series7, xadc.Xadc):
    db = Db("S7 applicative firmware")
    config_memory_size = 500*1024

    PART_NAMES = {
        "Spartan7-S6": "7s6",
        "Spartan7-S15": "7s15",
        "Spartan7-S25": "7s25",
        "Spartan7-S50": "7s50",
        "Spartan7-S75": "7s75",
        "Spartan7-S100": "7s100",
    }

    def __init__(self, port, index, idcode):
        series7.Series7.__init__(self, port, index, idcode)
        self.name = "Spartan7-" + parts[int(self.idcode.drop_revision())]

    def child_spawn(self, sub):
        return self.db.call(sub, self)
