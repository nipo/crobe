from .. import model
from ....part_id import PartId
from ...arm.coresight.rom_table import RomTable

__all__ = ["SoC"]

class SoC(model.SoC):
    def __init__(self, name, port):
        model.SoC.__init__(self, name)
        self.port = port

    def start(self):
        if not self.name:
            rts = self.port.children_find(lambda x: isinstance(x, RomTable))
            if rts:
                partid = rts[0].partid
                name = "Unknown SoC 0x%04x v. %d from %s (0x%08x)" % (partid.part_no, partid.revision, partid.manufacturer_name, int(partid))
                self.name = name

        model.SoC.start(self)
                
@SoC.db.register_default
def default_soc(dp):
    return SoC("", dp)

