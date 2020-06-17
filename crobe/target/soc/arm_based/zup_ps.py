from ....part_id import PartId
from .soc import SoC
import binascii

class ZupPs(SoC):
    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)

# Actually Xilinx screwed their root RomTable PID register (again)
# It actually decodes to 1/0x13/0x738
@SoC.db.register(PartId(1, 0x13, 0x738))
@SoC.db.register(PartId(1, 0x13, 0x711))
def zup_ps_probe(dp):
    return ZupPs("ZUP PS", dp)
