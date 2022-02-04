from ....component.arm.sw_dp import MultidropSwDp
from ....db import DisabledEntry
from ....part_id import PartId
from .soc import SoC

class RP2040(SoC):
    def __init__(self, swd):
        SoC.__init__(self, "RP2040", swd)

@SoC.db.register(PartId(9, 0x13, 0x1002))
def rp2040_probe(dp):
    if isinstance(dp, MultidropSwDp) and dp.targetsel.revision == 0:
        cpu0 = None
        cpu1 = None
        rescue = None

        for c in dp.port.children_of_class(MultidropSwDp):
            if c.targetsel == PartId(9, 0x13, 0x1002, 0xf):
                rescue = c
            elif c.targetsel == PartId(9, 0x13, 0x1002, 0):
                cpu0 = c
            elif c.targetsel == PartId(9, 0x13, 0x1002, 1):
                cpu1 = c

        if rescue and cpu0 and cpu1:
            return RP2040(dp.port)
    raise DisabledEntry()
