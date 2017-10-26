from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(0, 0x34, 0xe200))
def psoc63(dp):
    return SoC("PSoC-63", dp)
