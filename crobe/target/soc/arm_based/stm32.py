from ....part_id import PartId
from ....arm import ap
from ....adapter import jtag
from .soc import SoC

@jtag.Chain.db.register(PartId.from_idcode(0x06416041),
                        PartId.from_idcode(0x06418041))
def stm32_bs_irlen():
    return 5

@jtag.Tap.db.register(PartId.from_idcode(0x06416041),
                      PartId.from_idcode(0x06418041))
class Stm32Bs(jtag.Tap):
    def __init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post):
        jtag.Tap.__init__(self, port, idcode, ir_pre, ir_len, ir_post, dr_pre, dr_post)
        self.name = "STM32 Boundary Scan"

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
