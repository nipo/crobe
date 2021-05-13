from ...part_id import PartId
from ... import bitfield
from ...protocol import jtag
from . import series7, xadc
import pkg_resources

parts = {
    0x0362e093: "XC7A15T",
    0x0362d093: "XC7A35T",
}

@jtag.Chain.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Artix7(series7.Series7, xadc.Xadc):
    irlen = 6
    max_freq = 66e6
    config_memory_size = 4045564

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
        self.name = parts[int(self.idcode.drop_revision())]

    IR_XADC_DRP    = 0x37

    def spi_interface(self):
        from ...loadable.object import Program

        fw_name = "fw/" + self.name.lower() + "_jtag_spi.bit.gz"
        fd = pkg_resources.resource_filename(__name__, fw_name)
        self.load(Program.from_file(fd))

        from ..jtag_spi_bridge import JtagSpiBridge

        return JtagSpiBridge(self, self.IR_USER1, self.IR_USER2, 60e6)

    def child_spawn(self, mode = None):
        if mode == "spi":
            return self.spi_interface()
        return super().child_spawn(mode)

