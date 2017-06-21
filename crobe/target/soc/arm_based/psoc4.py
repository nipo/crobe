from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(0, 0x34, 0x9e)) # CYBL10563-56LQXI
def psoc4(dp):
    return SoC("PSoC4", dp)
