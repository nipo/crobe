from ....part_id import PartId
from ....arm import ap
from .soc import SoC

@SoC.db.register(PartId(0, 0x34, 0x161))
def psoc5(dp):
    return SoC("PSoC-5LP", dp)
