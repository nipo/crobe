from .... import model
from ....db import Db
from ....part_id import PartId
from ....arm.component.rom_table import RomTable

__all__ = ["SoC"]

def part_filter(id):
    return PartId(id.jep106_bank, id.jep106_id, id.part_no, 0)

class SoC(model.SoC):
    db = Db(id_filter = part_filter)

    def __init__(self, name, port):
        model.SoC.__init__(self, name)
        
        if not name:
            rts = self.children_find(lambda x: isinstance(x, RomTable))
            if rts:
                partid = rts[0].partid
                name = "Unknown part 0x%04x v. %d from %s (0x%08x)" % (partid.part_no, partid.revision, partid.manufacturer_name, int(partid))
                self.name = name

@SoC.db.register_default
def default_soc(dp):
    return SoC("", dp)

