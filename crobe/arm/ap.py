from . import dap
from ..db import Db
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
        self.port.run(ops)
        return ops[0].data

    def reg_write(self, addr, data):
        self.port.run([dap.ApWrite(addr, data, ap = self.index)])

    @property
    def idr(self):
        return self.reg_read(self.IDR)
    
    @classmethod
    def from_idr(cls, idr, dp, index):
        return cls.db.get(idr)(dp, index)

    def cast(self):
        try:
            return self.from_idr(self.idr, self.port, self.index)
        except KeyError:
            return self
