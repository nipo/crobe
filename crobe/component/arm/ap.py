from ...db import Db, NoMatch
from ...model import PortComponent

__all__ = ["Ap"]

class Ap(PortComponent):
    IDR = 0xfc

    db = Db(eq_func = lambda a, b: not ((a ^ b) & 0x0fffe00f))

    def __init__(self, dp, index = 0):
        PortComponent.__init__(self, "AP", dp)
        self.index = index
        self.components = []
        self.name = "AP (idr: 0x%08x)" % self.idr

    def reg_read(self, addr):
        op = self.cmd_read(addr)
        self.port.execute([op])
        return op.data

    def reg_write(self, addr, data):
        self.port.execute([self.cmd_write(addr, data)])

    @property
    def idr(self):
        return self.reg_read(self.IDR)
    
    def cast(self):
        try:
            return self.db.call(self.idr, self.port, self.index)
        except NoMatch:
            return self

    def cmd_write(self, addr, data):
        return self.port.cmd_ap_write(self.index, addr, data)

    def cmd_read(self, addr):
        return self.port.cmd_ap_read(self.index, addr)

    def cmd_run(self, cycles):
        return self.port.cmd_run(cycles)
