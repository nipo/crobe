from ...part_id import PartId
from ..arm.classic.jtag import Tap
from ..arm.classic.embedded_ice import *
from ...protocol import jtag

@jtag.Tap.db.register(PartId(0, 0x34, 0x7926))
class FX3(Tap):
    max_freq = 25e6

    def __init__(self, port, index, idcode):
        super().__init__(port, index, idcode, "FX3")
