from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(6, 0x73, 0x1))
def gecko(dp):
    return SoC("EFM32 Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0x81),
             PartId(6, 0x73, 0x82))
def leopard_gecko(dp):
    return SoC("EFM32 Leopard Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0xc9))
def flex_gecko(dp):
    return SoC("EFM32 Flex Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0x901))
def mighty_gecko(dp):
    return SoC("EFM32 Mighty Gecko", dp)
