from ...protocol import jtag
from ...part_id import PartId
from .stm32 import Info

@jtag.Chain.db.register(*[PartId(0, 0x20, 0x6000 | did)
                        for did in Info.parts.keys() if did])
class Stm32Bs(jtag.Tap):
    irlen = 5

    max_freq = 20e6
    
    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        info = Info.from_id(None, self.idcode.part_no)
        self.name = info.name + " Boundary Scan"
