from . import model
from ..component.xilinx.spartan6 import Spartan6
from ..component.xilinx.zynq import Zynq
from ..component.lattice.mach import MachXO2
from . import memory
import time

__all__ = []

@model.Target.register(Spartan6, Zynq, MachXO2)
class FpgaVolatileConfig(model.Target, memory.Loadable):
    """
    A volatile configuration for a FPGA
    """

    def __init__(self, comp):
        model.Target.__init__(self, "Volatile config for " + comp.name)
        memory.Loadable.__init__(self)
        self.component = comp

    def write(self, program,
              do_erase = False, do_verify = False,
              do_start = False, assume_clean = False):
        if do_erase:
            self.component.stop()
        if len(program):
            self.component.load(program)
