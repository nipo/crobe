from .model import MemoryMappedComponent
from ...part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x003, 0), # m3
    PartId(4, 0x3b, 0x00b, 0), # m0 BPU
    PartId(4, 0x3b, 0x00e, 0), # m7
    )
class Fpb(MemoryMappedComponent):
    CTRL = 0x000
    REMAP = 0x004
    COMP = lambda x: 0x008 + 4 * x

    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base)

        ctrl = self.reg_read(self.CTRL)
        self.lit_count = (ctrl >> 8) & 0xf
        self.code_count = ((ctrl >> 4) & 0xf) | ((ctrl >> 12) & 0x3)

    def __str__(self):
        return "Flash Patch and Breakpoint unit (%d litteral, %d code)" % (self.lit_count, self.code_count)
