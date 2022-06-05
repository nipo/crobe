from ....part_id import PartId
from .model import SoC

class Esp32c3(SoC):
    def __init__(self, name, dm):
        SoC.__init__(self, name, dm)

@SoC.db.register(PartId.from_idcode(0x00005c25))
def esp32c3_probe(dm):
    return Esp32c3("ESP32C3", dm)
