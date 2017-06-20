from ...adapter.protocol import jtag
from ...part_id import PartId

@jtag.Tap.db.register(PartId(0, 0x20, 0x6416),
                      PartId(0, 0x20, 0x6418))
class Stm32Bs(jtag.Tap):
    irlen = 5

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "STM32 Boundary Scan"
