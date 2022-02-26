from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
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

@jtag.Chain.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Zynq(series7.Series7, xadc.Xadc):
    irlen = 6
    max_freq = 66e6
    config_memory_size = 4045564

    class Efuse0(bitfield.Bitfield):
        all = bitfield.Field(0, 32)
        ForcePowerCycleReconfig        = bitfield.BooleanField(1)
        WenBKeyUser                    = bitfield.BooleanField(2, inverted = True)
        RenBKey                        = bitfield.BooleanField(3, inverted = True)
        RenBUser                       = bitfield.BooleanField(4, inverted = True)
        WenBCntl                       = bitfield.BooleanField(5, inverted = True)
        Unsup0                         = bitfield.BooleanField(6, inverted = True)
        Unsup1                         = bitfield.BooleanField(7, inverted = True)
        AESOnly                        = bitfield.BooleanField(8)
        JtagTAP                        = bitfield.BooleanField(9, inverted = True)
        BBRAMKey                       = bitfield.BooleanField(10, inverted = True)
        Repeat_ForcePowerCycleReconfig = bitfield.BooleanField(14+1)
        Repeat_WenBKeyUser             = bitfield.BooleanField(14+2, inverted = True)
        Repeat_RenBKey                 = bitfield.BooleanField(14+3, inverted = True)
        Repeat_RenBUser                = bitfield.BooleanField(14+4, inverted = True)
        Repeat_WenBCntl                = bitfield.BooleanField(14+5, inverted = True)
        Repeat_Unsup0                  = bitfield.BooleanField(14+6, inverted = True)
        Repeat_Unsup1                  = bitfield.BooleanField(14+7, inverted = True)
        Repeat_AESOnly                 = bitfield.BooleanField(14+8)
        Repeat_JtagTAP                 = bitfield.BooleanField(14+9, inverted = True)
        Repeat_BBRAMKey                = bitfield.BooleanField(14+10, inverted = True)

    def __init__(self, port, idcode):
        series7.Series7.__init__(self, port, idcode)
        self.name = "Zynq-" + parts[int(self.idcode.drop_revision())]

    IR_XADC_DRP    = jtag.Instruction(0x37, "XADC_DRP")
