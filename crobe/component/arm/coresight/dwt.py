from .model import MemoryMappedComponent
from .rom_table import RomTable
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x002), # m3
    PartId(4, 0x3b, 0x00a), # m0
    PartId(4, 0x3b, 0x1a02), # v8 Devarch
    )
@RomTable.soc_db.register(
    (PartId(4, 0x3b, 0x470), 0xe0001000,), # Cortex-M1 default ID
)
class Dwt(MemoryMappedComponent):
    CTRL = 0
    CTRL_CYCCNTENA          = 1 << 0
    CTRL_POSTPRESET = staticmethod(lambda x: x << 1)
    CTRL_POSTCNT = staticmethod(lambda x: x << 5)
    CTRL_CYCTAP             = 1 << 9
    CTRL_SYNCTAP_NONE       = 0x00000000 << 10
    CTRL_SYNCTAP_EVERY_16M  = 0x00000001 << 10
    CTRL_SYNCTAP_EVERY_64M  = 0x00000002 << 10
    CTRL_SYNCTAP_EVERY_256M = 0x00000003 << 10
    CTRL_PCSAMPLEENA        = 1 << 12
    CTRL_EXCTRCENA          = 1 << 16
    CTRL_CPIEVTENA          = 1 << 17
    CTRL_EXCEVTENA          = 1 << 18
    CTRL_SLEEPEVTENA        = 1 << 19
    CTRL_LSUEVTENA          = 1 << 20
    CTRL_FOLDEVTENA         = 1 << 21
    
    CYCCNT = 0x004
    CPICNT = 0x008
    EXCCNT = 0x00c
    SLEEPCNT = 0x010
    LSUCNT = 0x014
    FOLDCNT = 0x018
    PCSR = 0x01c
    COMP = staticmethod(lambda x: 0x020 + 0x10 * x)
    MASK = staticmethod(lambda x: 0x024 + 0x10 * x)
    FUNCTION = staticmethod(lambda x: 0x028 + 0x10 * x)

    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "DWT")

        ctrl = self.reg_read(self.CTRL)

        self.comparator_count = ctrl >> 28
        self.trigger_available = not (ctrl & 0x0f000000)

        self.logger.note("%d comparators%s", 
                         self.comparator_count,
                         ["", ", triggers"][self.trigger_available])

    def __str__(self):
        return "Data Watch Trace Unit"

    def trace_enable(self):
        self.reg_write(self.CTRL, 0
                       | self.CTRL_SYNCTAP_EVERY_64M
                       | self.CTRL_PCSAMPLEENA
                       | self.CTRL_CYCCNTENA
                       | self.CTRL_CYCTAP
                       | self.CTRL_POSTCNT(0)
                       | self.CTRL_EXCTRCENA
                       )
        self.logger.note("CTRL: 0x%08x", self.reg_read(self.CTRL))
