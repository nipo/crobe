from . import model
from ..component.model import SramFpga
from . import memory
import time

__all__ = []

@model.Target.register(SramFpga)
class FpgaVolatileConfig(model.Target, memory.Loadable):
    """
    A volatile configuration for a FPGA
    """

    def __init__(self, comp):
        model.Target.__init__(self, "SRAM config of " + comp.name)
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

