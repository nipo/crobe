from ...part_id import PartId
from ...protocol import swd

for i in range(0, 32*16*4):
    for j in [0, 15]:
        swd.Interface.targetsel_db._register([PartId(2, 0x44, i, j)], "nRF7002")
