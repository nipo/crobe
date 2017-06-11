from ....part_id import PartId
from ....arm import ap
from .soc import SoC

@SoC.db.register(PartId(0, 0x20, 0x449, 0))
def stm32f74x(dp):
    return SoC("STM32F74x", dp)

@SoC.db.register(PartId(0, 0x20, 0x413, 0),
             PartId(0, 0x20, 0x423, 0),
             PartId(0, 0x20, 0x433, 0),
             PartId(0, 0x20, 0x411, 0))
def stm32f40x(dp):
    return SoC("STM32F40x/41x", dp)

@SoC.db.register(PartId(0, 0x20, 0x419, 0))
def stm32f42x(dp):
    return SoC("STM32F42x/43x", dp)

@SoC.db.register(PartId(0, 0x20, 0x410, 0),
             PartId(0, 0x20, 0x412, 0),
             PartId(0, 0x20, 0x414, 0),
             PartId(0, 0x20, 0x430, 0),
             PartId(0, 0x20, 0x418, 0),
             PartId(0, 0x20, 0x410, 0))
def std32f10x(dp):
    return SoC("STM32F10x", dp)

@SoC.db.register(PartId(0, 0x20, 0x416, 0),
             PartId(0, 0x20, 0x429, 0),
             PartId(0, 0x20, 0x427, 0),
             PartId(0, 0x20, 0x436, 0),
             PartId(0, 0x20, 0x437, 0))
def std32l10x(dp):
    return SoC("STM32L10x", dp)
