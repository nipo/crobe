from . import model
from ..component.xilinx.spartan6 import Spartan6
from ..component.xilinx.spartan7 import Spartan7
from ..component.xilinx.artix7 import Artix7
from ..component.xilinx.zynq import Zynq
from ..component.lattice.mach import MachXO2
from ..component.lattice.ice40 import Ice40SlaveSerial
from . import memory
import time

__all__ = []

@model.Target.register(Spartan6, Spartan7, Zynq, MachXO2, Ice40SlaveSerial, Artix7)
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

    def reset(self):
        self.component.reset()

