from . import model
from ..component.xilinx.spartan6 import Spartan6
from ..component.xilinx.zynq import Zynq
from ..component.lattice.mach import MachXO2
from . import memory

__all__ = ["Fpga"]

class Config(memory.Region):
    type = memory.Type.RAM
    flags = set([memory.Flag.WRITABLE, memory.Flag.VOLATILE])

    def __init__(self, fpga):
        memory.Region.__init__(self, "config", 0, fpga.config_memory_size)
        self.fpga = fpga

    def erase(self, offset, size):
        print("erase")
        self.fpga.stop()

    def write(self, offset, data):
        print("write", offset, data)
        self.fpga.config_write(data)

@model.Target.register(Spartan6, Zynq)
class Fpga(model.Target, memory.Loadable):
    """
    A FPGA
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        memory.Loadable.__init__(self)
        self.child_add(Config(comp))
        self.component = comp

class MachFlash(memory.Region):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE])

    def __init__(self, fpga, name, offset, size):
        memory.Region.__init__(self, name, offset, size)
        self.fpga = fpga

    def erase(self, offset, size):
        self.fpga.stop()

    def write(self, offset, data):
        self.fpga.config_write(data)

class MachConfigFlash(MachFlash):
    def __init__(self, fpga):
        MachFlash.__init__(self, fpga, "config", 0, fpga.info.flash_page_count * 16)

class MachUfmFlash(MachFlash):
    def __init__(self, fpga):
        MachFlash.__init__(self, fpga, "ufm", fpga.info.flash_page_count * 16, fpga.info.ufm_page_count * 16)

@model.Target.register(MachXO2)
class MachXO(model.Target, memory.Loadable):
    """
    Mach-XO2 target
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        memory.Loadable.__init__(self)
#        self.child_add(MachConfigFlash(comp))
#        if comp.info.ufm_page_count:
#            self.child_add(MachUfmFlash(comp))
        self.child_add(Config(comp))
        self.component = comp

    def erase_all(self):
        self.component.stop()

    def write(self, program):
        self.component.config_write(program)
