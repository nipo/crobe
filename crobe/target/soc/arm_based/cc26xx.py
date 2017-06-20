from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(0, 0x17, 0xb99a)) # cc2650
def cc26xx(dp):
    return SoC("CC26xx", dp)

@SoC.db.register(PartId(0, 0x17, 0xb9be)) # cc1310
def cc13xx(dp):
    return SoC("CC13xx", dp)
