from .model import MemoryMappedComponent

@MemoryMappedComponent.db.register(
    0x4000bb001,
    0x4002bb001,
    0x4001bb001,
    0x4003bb001,
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
