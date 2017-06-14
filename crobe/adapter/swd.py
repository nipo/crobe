from . import model
from .. import bitstring
import time

__all__ = ["Read", "Write", "JtagToSwd", "Wakeup"]

class Interface(model.Interface):
    def __init__(self, port):
        model.Interface.__init__(self, "SWD Intf", port)

    def start(self):
        from ..arm import dap

        self.port.reset = True
        time.sleep(.005)
        self.port.reset = False
        time.sleep(.050)
        
        self.children.append(dap.Dap(self))

        model.Interface.start(self)
        
    def execute(self, operation_list):
        raise NotImplementedError()

    def read(self, ap, addr):
        op = Read(ap, addr)
        self.execute([op])
        return op.data

    def write(self, ap, addr, data):
        self.execute([Write(ap, addr, data)])

    def run(self, cycles):
        self.execute([Run(cycles)])

    def jtag_to_swd(self):
        self.execute([JtagToSwd()])

    def wakeup(self):
        self.execute([Wakeup()])
    
class Operation(object):
    def __repr__(self):
        return str(self)

class Read(Operation):
    def __init__(self, ap, addr):
        self.ap = ap
        self.addr = addr

    # When executed
    data = None

    def __str__(self):
        if self.ap:
            return "<Read AP 0x%x>" % (self.addr * 4)
        else:
            return "<Read DP 0x%x>" % (self.addr)
        
class Write(Operation):
    def __init__(self, ap, addr, data):
        self.ap = ap
        self.addr = addr
        self.data = data

    def __str__(self):
        if self.ap:
            return "<Write AP 0x%x 0x%08x>" % (self.addr * 4, self.data)
        else:
            return "<Write DP 0x%x 0x%08x>" % (self.addr, self.data)

class JtagToSwd(Operation):
    def __str__(self):
        return "<JTAG to SWD>"

    out = bitstring.BitString(0b1110011110011110, 16)

class Wakeup(Operation):
    def __str__(self):
        return "<SWD Wakeup>"

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles
