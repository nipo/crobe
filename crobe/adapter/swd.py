from . import model

__all__ = ["Read", "Write", "JtagToSwd", "Wakeup"]

class Interface(model.Interface):
    def __init__(self):
        pass

    def run(self, operation_list):
        raise NotImplementedError()

class Operation(object):
    pass

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

class Wakeup(Operation):
    def __str__(self):
        return "<SWD Wakeup>"
