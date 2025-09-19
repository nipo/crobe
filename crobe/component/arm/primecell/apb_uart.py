from ..coresight.model import MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(PartId(4, 0x3b, 0x821))
class ApbUart(MemoryMappedComponent):
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "ApbUart")
