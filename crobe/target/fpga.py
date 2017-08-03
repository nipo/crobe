from . import model
from ..component.xilinx.spartan6 import Spartan6
from . import loadable

__all__ = ["Fpga"]

@model.Target.register(Spartan6)
class SpiFlash(model.Target, loadable.Loadable):
    """
    A FPGA
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        self.component = comp
    
    def read(self, address, size):
        raise NotImplementedError("Cannot read FPGA")

    def erase_all(self):
        self.component.stop()

    def write(self, program, erase_first = True, verify = False):
        return self.component.load(program)

    def verify(self, program):
        raise NotImplementedError("Cannot verify FPGA")

