from ....part_id import PartId
from .model import SoC

class NeoRV32(SoC):
    def __init__(self, name, dm):
        SoC.__init__(self, name, dm)

@SoC.db.register(PartId.from_idcode(0x0cafe001))
def neorv32_probe(dm):
    return NeoRV32("NeoRV32 demo", dm)
