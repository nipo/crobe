from . import model

__all__ = ["CaptureDr", "CaptureIr", "Shift", "Reset", "Run", "SwdToJtag"]

class Interface(model.Interface):
    def __init__(self):
        pass

    def run(self, operation_list):
        raise NotImplementedError()

class Operation(object):
    def __init__(self):
        pass

class CaptureDr(Operation):
    def __str__(self):
        return "<Capture DR>"

class CaptureIr(Operation):
    def __str__(self):
        return "<Capture IR>"

class SwdToJtag(Operation):
    def __str__(self):
        return "<SWD to JTAG>"

class Shift(Operation):
    def __init__(self, tdi, length, read_tdo = True):
        self.tdi = tdi
        self.length = length
        self.read_tdo = tdo

    # When done, if requested:
    tdo = None

    def __str__(self):
        return "<Shift %s>" % (self.tdi)

class Reset(Operation):
    def __str__(self):
        return "<TAP Reset>"

class Run(Operation):
    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "<Run %d>" % self.cycles
