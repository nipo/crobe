from .model import MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x003), # m3
    PartId(4, 0x3b, 0x00b), # m0 BPU
    PartId(4, 0x3b, 0x00e), # m7
    )
class Fpb(MemoryMappedComponent):
    CTRL = 0x000
    REMAP = 0x004
    COMP = lambda x: 0x008 + 4 * x

    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "FPB")

        ctrl = self.reg_read(self.CTRL)
        self.lit_count = (ctrl >> 8) & 0xf
        self.code_count = ((ctrl >> 4) & 0xf) | ((ctrl >> 12) & 0x3)

        self.logger.info("%d litteral, %d code", self.lit_count, self.code_count)

    def enable(self):
        self.reg_write(self.CTRL, 0x3)

    def disable(self):
        self.reg_write(self.CTRL, 0x2)
        
    def __str__(self):
        return "Flash Patch and Breakpoint unit"
