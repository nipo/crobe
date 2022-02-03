from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ...db import Db, NoMatch
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
    config_memory_size = 500*1024

    PART_NAMES = {
        "Spartan7-S6": "7s6",
        "Spartan7-S15": "7s15",
        "Spartan7-S25": "7s25",
        "Spartan7-S50": "7s50",
        "Spartan7-S75": "7s75",
        "Spartan7-S100": "7s100",
    }

    class Efuse0(bitfield.Bitfield):
        all = bitfield.Field(0, 32)
        AESOnly                        = bitfield.BooleanField(0)
        AESExclusive                   = bitfield.BooleanField(1)
        WenBKeyUser                    = bitfield.BooleanField(2, inverted = True)
        RenBKey                        = bitfield.BooleanField(3, inverted = True)
        RenBUser                       = bitfield.BooleanField(4, inverted = True)
        WenBCntl                       = bitfield.BooleanField(5, inverted = True)
        Unsup0                         = bitfield.BooleanField(6)
        Unsup1                         = bitfield.BooleanField(7)
        Unsup2                         = bitfield.BooleanField(8)
        Unsup3                         = bitfield.BooleanField(9)
        BBRAMKey                       = bitfield.BooleanField(10, inverted = True)
        Repeat_AESOnly                 = bitfield.BooleanField(14+0)
        Repeat_AESExclusive            = bitfield.BooleanField(14+1)
        Repeat_WenBKeyUser             = bitfield.BooleanField(14+2, inverted = True)
        Repeat_RenBKey                 = bitfield.BooleanField(14+3, inverted = True)
        Repeat_RenBUser                = bitfield.BooleanField(14+4, inverted = True)
        Repeat_WenBCntl                = bitfield.BooleanField(14+5, inverted = True)
        Repeat_Unsup0                  = bitfield.BooleanField(14+6)
        Repeat_Unsup1                  = bitfield.BooleanField(14+7)
        Repeat_Unsup2                  = bitfield.BooleanField(14+8)
        Repeat_Unsup3                  = bitfield.BooleanField(14+9)
        Repeat_BBRAMKey                = bitfield.BooleanField(14+10, inverted = True)

    def __init__(self, port, index, idcode):
        series7.Series7.__init__(self, port, index, idcode)
        self.name = "Spartan7-" + parts[int(self.idcode.drop_revision())]
