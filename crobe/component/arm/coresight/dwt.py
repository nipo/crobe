from .model import MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x002), # m3
    PartId(4, 0x3b, 0x00a), # m0
    )
class Dwt(MemoryMappedComponent):
    CTRL = 0
    CYCCNT = 0x004
    CPICNT = 0x008
    EXCCNT = 0x00c
    SLEEPCNT = 0x010
    LSUCNT = 0x014
    FOLDCNT = 0x018
    PCSR = 0x01c
    COMP = lambda x: 0x020 + 0x10 * x
    MASK = lambda x: 0x024 + 0x10 * x
    FUNCTION = lambda x: 0x028 + 0x10 * x

    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base)

        ctrl = self.reg_read(self.CTRL)

        self.comparator_count = ctrl >> 28
        self.trigger_available = not (ctrl & 0x0f000000)

    def __str__(self):
        return "Data Watch Trace unit (%d comparators%s)" % (
            self.comparator_count, ["", ", triggers"][self.trigger_available])
