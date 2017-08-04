from . import model
from ..component.xilinx.spartan6 import Spartan6
from . import memory

__all__ = ["Fpga"]

class Config(memory.Region):
    type = memory.Type.RAM
    flags = set([memory.Flag.WRITABLE, memory.Flag.VOLATILE])

    def __init__(self, fpga):
        memory.Region.__init__(self, "config", 0, 500*1024)
        self.fpga = fpga

    def erase(self, offset, size):
        self.fpga.stop()

    def write(self, offset, data):
        self.fpga.config_write(data)

@model.Target.register(Spartan6)
class SpiFlash(model.Target, memory.Loadable):
    """
    A FPGA
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        memory.Loadable.__init__(self)
        self.child_add(Config(comp))
        self.component = comp

