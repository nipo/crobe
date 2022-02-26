from .model import CoresightComponent, MemoryMappedComponent
from ....part_id import PartId

@MemoryMappedComponent.db.register(
    PartId(4, 0x3b, 0x001),
    PartId(4, 0x3b, 0x913),
    PartId(4, 0x3b, 0x1a01), # v8 Devarch
    )
class Itm(CoresightComponent):
    STIM = staticmethod(lambda x: 4 * x)

    ER = 0xe00
    
    PR = 0xe40

    CR = 0xe80
    CR_DWTENA  = 0x08
    CR_ITMENA  = 0x01
    CR_SYNCENA = 0x04
    CR_TSENA   = 0x02
    CR_SWOENA  = 0x10
    CR_TRACEBUSID = staticmethod(lambda x: x << 16)
    CR_TSPRESCALE = staticmethod(lambda x: x << 8)

    SCR = 0xe90
    SCR_SYNC_COUNT_MASK = 0x3ff
    
    def __init__(self, ap, base):
        MemoryMappedComponent.__init__(self, ap, base, "ITM")

    def __str__(self):
        return "Instruction Trace Macrocell"

    def trace_enable(self, id = None):
        with self.access():
            self.reg_write(self.CR, 0
                           | self.CR_DWTENA
                           | self.CR_ITMENA
                           | self.CR_SYNCENA
                           | self.CR_TRACEBUSID(id)
                           )
            self.reg_write(self.ER, 0xffffffff);
            self.reg_write(self.SCR, 0xff);
            self.logger.note("CR: 0x%08x", self.reg_read(self.CR))
            self.logger.note("SCR: 0x%08x", self.reg_read(self.SCR))
            self.logger.note("ER: 0x%08x", self.reg_read(self.ER))
