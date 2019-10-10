from ...part_id import PartId
from ...protocol import jtag

@jtag.Tap.db.register(PartId.from_idcode(0x01434093).drop_revision())
class Spartan3(jtag.Tap):
    irlen = 6
    max_freq = 33e6
