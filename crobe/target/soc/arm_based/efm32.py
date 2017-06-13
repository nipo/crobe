from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(6, 0x73, 0x1, 0))
def gecko(dp):
    return SoC("EFM32 Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0x81, 0),
             PartId(6, 0x73, 0x82, 0))
def leopard_gecko(dp):
    return SoC("EFM32 Leopard Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0xc9, 0))
def flex_gecko(dp):
    return SoC("EFM32 Flex Gecko", dp)

@SoC.db.register(PartId(6, 0x73, 0x901, 0))
def mighty_gecko(dp):
    return SoC("EFM32 Mighty Gecko", dp)
