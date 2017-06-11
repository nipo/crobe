from .... import model
from ....db import Db
from ....part_id import PartId

__all__ = ["SoC"]

def part_filter(id):
    return PartId(id.jep106_bank, id.jep106_id, id.part_no, 0)

class SoC(model.SoC):
    db = Db(id_filter = part_filter)

    def __init__(self, name, port):
        model.SoC.__init__(self, name)

        self.children.append(port)

@SoC.db.register_default
def default_soc(dp):
    return SoC("Unknown", dp)

