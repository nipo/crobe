from ....part_id import PartId
from .soc import SoC

# Actually Xilinx screwed their root RomTable PID register
# It actually decodes to Ikanos/0x3b2
@SoC.db.register(PartId.from_idcode(0x003b2313))
def ZynqPs(dp):
    return SoC("Zynq PS", dp)
