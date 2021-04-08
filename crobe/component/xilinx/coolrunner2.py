from ...part_id import PartId
from ...protocol import jtag

@jtag.Chain.db.register(PartId.from_idcode(0x06e59093).drop_revision())
class Coolrunner2(jtag.Tap):
    irlen = 8
    max_freq = 33e6
