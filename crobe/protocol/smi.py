from . import base
from .. import bitstring
from ..db import Db, NoMatch
from ..model import PortComponent

__all__ = ["Interface"]

class ProtocolError(base.ProtocolError):
    pass

class Interface(base.Interface):
    """
    SMI protocol interface.
    """

    db = Db("SMI chip type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/SMI")

    def start(self):
        self.freq_cap("IEEE", 25e6)
        base.Interface.start(self)
        
    def _execute(self, operation_list):
        """
        Executes a row of operations, starting with a start condition,
        stopping with a stop condition, with restarts in the middle.
        """
        raise NotImplementedError()

    def c22_read(self, phyad, addr):
        """
        See cmd_c22_read()
        """
        op = self.cmd_c22_read(phyad, addr)
        self.execute([op])
        self.logger.debug("> C22 Phy 0x%02x Reg 0x%20x: %04x", phyad, addr, op.data)
        return op.data

    def c22_write(self, phyad, addr, data):
        """
        See cmd_c22_write()
        """
        op = self.cmd_c22_write(phyad, addr, data)
        self.logger.debug("< C22 Prt 0x%02x Dev 0x%20x: %04x", phyad, addr, data)
        self.execute([op])

    def c45_read(self, prtad, devad):
        """
        See cmd_c45_read()
        """
        op = self.cmd_c45_read(prtad, devad)
        self.execute([op])
        self.logger.debug("> C45 Prt 0x%02x Dev 0x%20x: %04x", prtad, devad, op.data)
        return op.data

    def c45_read_inc(self, prtad, devad):
        """
        See cmd_c45_read_inc()
        """
        op = self.cmd_c45_read_inc(prtad, devad)
        self.execute([op])
        self.logger.debug("> C45+ Prt 0x%02x Dev 0x%20x: %04x", prtad, devad, op.data)
        return op.data

    def c45_addr(self, prtad, devad, addr):
        """
        See cmd_c45_addr()
        """
        op = self.cmd_c45_addr(prtad, devad, addr)
        self.logger.debug("< C45 Prt 0x%02x Dev 0x%20x @%04x", prtad, devad, addr)
        self.execute([op])

    def c45_write(self, prtad, devad, data):
        """
        See cmd_c45_write()
        """
        op = self.cmd_c45_addr(prtad, devad, data)
        self.logger.debug("< C45 Prt 0x%02x Dev 0x%20x: %04x", prtad, devad, data)
        self.execute([op])

    def cmd_c22_read(self, phyad, addr):
        """
        Clause 22 read
        """
        return C22Read(phyad, addr)

    def cmd_c22_write(self, phyad, addr, data):
        """
        Clause 22 write
        """
        return C22Write(phyad, addr, data)

    def cmd_c45_read(self, prtad, devad):
        """
        Clause 45 Read
        """
        return C45Read(prtad, devad)

    def cmd_c45_read_inc(self, prtad, devad):
        """
        Clause 45 Read with increment
        """
        return C45ReadInc(prtad, devad)

    def cmd_c45_addr(self, prtad, devad, addr):
        """
        Clause 45 Address
        """
        return C45Addr(prtad, devad, addr)

    def cmd_c45_write(self, prtad, devad, data):
        """
        Clause 45 Write
        """
        return C45Addr(prtad, devad, data)

    def child_spawn(self, sub):
        try:
            return self.db.call(sub, self)
        except NoMatch:
            return

class C22Slave(PortComponent):
    def __init__(self, port, name = "slave", phyad = None):
        super().__init__(port, name)
        self.phyad = phyad

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'phyad':
            self.phyad = int(v, 16)
            return
        PortComponent.option_set(self, opt)

    def read(self, addr):
        return self.port.c22_read(self.phyad, addr)

    def write(self, addr, data):
        return self.port.c22_write(self.phyad, addr, data)

    def ext_read(self, devad, address):
        dev = self.cmd_write(13, devad)
        addr = self.cmd_write(14, address)
        dev2 = self.cmd_write(13, 0x4000 | devad)
        rdata = self.cmd_read(14)
        self.execute([dev, addr, dev2, rdata])
        return rdata.data

    def ext_write(self, devad, address, data):
        dev = self.cmd_write(13, devad)
        addr = self.cmd_write(14, address)
        dev2 = self.cmd_write(13, 0x4000 | devad)
        data = self.cmd_write(14, data)
        self.execute([dev, addr, dev2, data])
    
    def cmd_read(self, addr):
        return self.port.cmd_c22_read(self.phyad, addr)

    def cmd_write(self, addr, data):
        return self.port.cmd_c22_write(self.phyad, addr, data)

    def execute(self, ops):
        return self.port.execute(ops)

    def __str__(self):
        return f"{self.name}@{self.phyad:x}"
        
class Operation(object):
    def __repr__(self):
        return str(self)

class C22Read(Operation):
    def __init__(self, phyad, addr):
        self.phyad = phyad
        self.addr = addr

    # When executed
    data = None

    def __str__(self):
        return "<C22 Read 0x%x 0x%x>" % (self.phyad, self.addr)

class C45Read(Operation):
    def __init__(self, prtad, devad):
        self.prtad = prtad
        self.devad = devad

    # When executed
    data = None

    def __str__(self):
        return "<C45 Read 0x%x 0x%x>" % (self.prtad, self.devad)

class C45ReadInc(Operation):
    def __init__(self, prtad, devad):
        self.prtad = prtad
        self.devad = devad

    # When executed
    data = None

    def __str__(self):
        return "<C45 ReadInc 0x%x 0x%x>" % (self.prtad, self.devad)

class C22Write(Operation):
    def __init__(self, phyad, addr, data):
        self.phyad = phyad
        self.addr = addr
        self.data = data

    def __str__(self):
        return "<C22 Write 0x%x 0x%x>" % (self.phyad, self.addr, self.data)

class C45Write(Operation):
    def __init__(self, prtad, devad, data):
        self.prtad = prtad
        self.devad = devad
        self.data = data

    def __str__(self):
        return "<C45 Write 0x%x 0x%x 0x%04x>" % (self.prtad, self.devad, self.data)

class C45Addr(Operation):
    def __init__(self, prtad, devad, addr):
        self.prtad = prtad
        self.devad = devad
        self.addr = addr

    def __str__(self):
        return "<C45 Addr 0x%x 0x%x 0x%04x>" % (self.prtad, self.devad, self.addr)

