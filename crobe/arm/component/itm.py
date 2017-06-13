from .model import MemoryMappedComponent
from ...part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x001, 0),
    PartId(4, 0x3b, 0x913, 0),
    )
class Itm(MemoryMappedComponent):
    STIM = lambda x: 4 * x
    TER = 0xe00
    TPR = 0xe40
    TCR = 0xe80
    
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base)

    def __str__(self):
        return "Instruction Trace Macrocell"
