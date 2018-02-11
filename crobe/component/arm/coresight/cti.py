from .model import CoresightComponent
from ....part_id import PartId

@CoresightComponent.db.register(
    0x14, # a9 CTI
    )
class Cti(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base, "Cross-Trigger Interface")

