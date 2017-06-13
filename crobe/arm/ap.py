from . import dap
from ..db import Db, NoMatch
from ..model import PortComponent

__all__ = ["Ap", "db"]

class Ap(PortComponent):
    IDR = 0xfc

    db = Db(id_filter = lambda idr: idr & 0x0fffe00f)

    def __init__(self, dp, index = 0):
        PortComponent.__init__(self, "AP", dp)
        self.index = index
        self.components = []
        self.name = "AP (idr: 0x%08x)" % self.idr

    def reg_read(self, addr):
        ops = [dap.ApRead(addr, ap = self.index)]
        self.port.execute(ops)
        return ops[0].data

    def reg_write(self, addr, data):
        self.port.execute([dap.ApWrite(addr, data, ap = self.index)])

    @property
    def idr(self):
        return self.reg_read(self.IDR)
    
    def cast(self):
        try:
            return self.db.call(self.idr, self.port, self.index)
        except NoMatch:
            return self
