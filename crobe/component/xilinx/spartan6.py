from ...part_id import PartId
from ...protocol import jtag
import os, os.path
from . import series6

parts = {
    0x04000093: "LX4",
    0x04001093: "LX9",
    0x04002093: "LX16",
    0x04004093: "LX25",
    0x04024093: "LX25T",
    0x04008093: "LX45",
    0x04028093: "LX45T",
    0x0400E093: "LX75",
    0x0402E093: "LX75T",
    0x04011093: "LX100",
    0x04031093: "LX100T",
    0x0401D093: "LX150",
    0x0403D093: "LX150T",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Spartan6(series6.Series6):
    base_path = os.path.join(os.path.dirname(__file__), "fw")
    config_memory_size = 500*1024

    PART_NAMES = {
        "Spartan6-LX4": "6slx4",
        "Spartan6-LX9": "6slx9",
        "Spartan6-LX16": "6slx16",
        "Spartan6-LX25": "6slx25",
        "Spartan6-LX25T": "6slx25t",
        "Spartan6-LX45": "6slx45",
        "Spartan6-LX45T": "6slx45t",
        "Spartan6-LX75": "6slx75",
        "Spartan6-LX75T": "6slx75t",
        "Spartan6-LX100": "6slx100",
        "Spartan6-LX100T": "6slx100t",
        "Spartan6-LX150": "6slx150",
        "Spartan6-LX150T": "6slx150t",
    }

    def __init__(self, port, index):
        series6.Series6.__init__(self, port, index)
        self.name = "Spartan6-" + parts[int(port.idcode_at(index).drop_revision())]

    def spi_interface(self):
        from ...loadable.object import Program
        filename = os.path.join(self.base_path, self.name.lower() + "_jtag_spi.bit.gz")
        self.load(Program.from_file(filename))

        from ..jtag_spi_bridge import JtagSpiBridge

        return JtagSpiBridge(self, self.IR_USER1, self.IR_USER2, 50e6)

    def child_spawn(self, mode = None):
        if mode == "spi":
            return self.spi_interface()
