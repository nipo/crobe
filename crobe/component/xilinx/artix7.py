from ...part_id import PartId
from ...protocol import jtag
from . import series7, xadc
import pkg_resources

parts = {
    0x0362e093: "XC7A15T",
    0x0362d093: "XC7A35T",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Artix7(series7.Series7, xadc.Xadc):
    irlen = 6
    max_freq = 66e6
    config_memory_size = 4045564

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
