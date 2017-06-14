from ....part_id import PartId
from ....arm import ap
from ....adapter import jtag
from .soc import SoC

@jtag.Tap.db.register(PartId(0, 0x20, 0x6416),
                      PartId(0, 0x20, 0x6418))
class Stm32Bs(jtag.Tap):
    irlen = 5

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "STM32 Boundary Scan"

@SoC.db.register(PartId(0, 0x20, 0x449))
def stm32f74x(dp):
    return SoC("STM32F74x", dp)

@SoC.db.register(PartId(0, 0x20, 0x413),
             PartId(0, 0x20, 0x423),
             PartId(0, 0x20, 0x433),
             PartId(0, 0x20, 0x411))
def stm32f40x(dp):
    return SoC("STM32F40x/41x", dp)

@SoC.db.register(PartId(0, 0x20, 0x419))
def stm32f42x(dp):
    return SoC("STM32F42x/43x", dp)

@SoC.db.register(PartId(0, 0x20, 0x410),
             PartId(0, 0x20, 0x412),
             PartId(0, 0x20, 0x414),
             PartId(0, 0x20, 0x430),
             PartId(0, 0x20, 0x418),
             PartId(0, 0x20, 0x410))
def std32f10x(dp):
    return SoC("STM32F10x", dp)

@SoC.db.register(PartId(0, 0x20, 0x416),
             PartId(0, 0x20, 0x429),
             PartId(0, 0x20, 0x427),
             PartId(0, 0x20, 0x436),
             PartId(0, 0x20, 0x437))
def std32l10x(dp):
    return SoC("STM32L10x", dp)
