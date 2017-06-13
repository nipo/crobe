from ...part_id import PartId
from ...adapter import jtag

@jtag.Chain.db.register(PartId.from_idcode(0x24001093))
def xc6_bs_irlen():
    return 6

@jtag.Tap.db.register(PartId.from_idcode(0x24001093))
class Spartan6(jtag.Tap):
    def __init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post):
        jtag.Tap.__init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post)
        self.name = "Spartan-6"
