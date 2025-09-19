from ....part_id import PartId
from .soc import SoC
from ....component.arm.coresight.dwt import Dwt
from ....component.arm.coresight.fpb import Fpb
from ....component.arm.coresight.scs import Scs

@SoC.db.register(PartId(4, 0x3b, 0x470))
class CortexM1SDK(SoC):
    def __init__(self, dp):
        SoC.__init__(self, "CortexM1SDK", dp)
