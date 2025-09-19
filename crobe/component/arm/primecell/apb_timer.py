from ..coresight.model import MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(PartId(4, 0x3b, 0x22))
class ApbTimer(MemoryMappedComponent):
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "ApbTimer")
