from ...protocol import jtag
from ...part_id import PartId
from .stm32 import Info

@jtag.Tap.db.register(*[PartId(0, 0x20, 0x6000 | did)
                        for did in Info.parts.keys() if did])
class Stm32Bs(jtag.Tap):
    irlen = 5

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        info = Info.from_id(port.idcode_at(index).part_no)
        self.name = info.name + " Boundary Scan"
