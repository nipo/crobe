from .model import MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x003), # m3
    PartId(4, 0x3b, 0x00b), # m0 BPU
    PartId(4, 0x3b, 0x00e), # m7
    PartId(4, 0x3b, 0x1a03), # v8 Devarch
    )
class Fpb(MemoryMappedComponent):
    CTRL = 0x000
    REMAP = 0x004
    COMP = staticmethod(lambda x: 0x008 + 4 * x)

    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "FPB")

        ctrl = self.reg_read(self.CTRL)
        self.lit_count = (ctrl >> 8) & 0xf
        self.code_count = ((ctrl >> 4) & 0xf) | ((ctrl >> 12) & 0x3)

        self.logger.note("%d litteral, %d code", self.lit_count, self.code_count)

    def enable(self, enable = True):
        self.reg_write(self.CTRL, 0x3 if enable else 0)

    def is_enabled(self):
        return self.reg_read(self.CTRL) & 1
        
    def comp_set(self, index, addr = None):
        if index >= self.code_count:
            raise ValueError(index)

        if addr is not None:
            value = addr | 1
        else:
            value = 0
        self.reg_write(self.COMP(index), value)

    def comp_get(self, index):
        if index >= self.code_count:
            raise ValueError(index)

        value = self.COMP(index)
        if value & 1:
            return value & ~1
        return None

    def comp_clear(self):
        for index in range(self.code_count):
            self.reg_write(self.COMP(index), 0)
        
        
    def __str__(self):
        return "Flash Patch and Breakpoint unit"
