from . import model
from ..component.xilinx.spartan6 import Spartan6
from ..component.xilinx.zynq import Zynq
from ..component.lattice.mach import MachXO2Config
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

    def write(self, program):
        self.component.load(program)

class MachMem(memory.Region):
    def __init__(self, fpga, name, offset, size):
        memory.Region.__init__(self, name, offset, size)
        self.fpga = fpga

class MachConfig(MachMem):
    type = memory.Type.RAM
    flags = set([memory.Flag.WRITABLE])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "config", 0, fpga.info.flash_page_count * 16)

    def erase(self, offset, size):
        self.fpga.stop()

    def write(self, offset, data):
        self.fpga.config_write(data)

class MachFlash(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "flash", 0x20000000, fpga.info.flash_page_count * 16)

    def erase(self, offset, size):
        if offset == 0:
            self.fpga.flash_erase()

    def write(self, offset, data):
        self.fpga.flash_write(offset, data)

    def read(self, offset, length):
        return self.fpga.flash_read(offset, length)

class MachUfm(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "ufm", 0x20000000 + fpga.info.flash_page_count * 16, fpga.info.ufm_page_count * 16)

    def erase(self, offset, size):
        if offset == 0:
            self.fpga.ufm_erase()

    def write(self, offset, data):
        self.fpga.ufm_write(offset, data)

    def read(self, offset, length):
        return self.fpga.ufm_read(offset, length)

class MachFeature(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "Feature", 0x10000000, 8)

    def erase(self, offset, size):
        self.fpga.feature_erase()

    def read(self, offset, length):
        assert offset == 0 and length == 8
        return self.fpga.feature_read()

    def write(self, offset, data):
        assert offset == 0 and len(data) == 8

        self.fpga.feature_write(data)

@model.Target.register(MachXO2Config)
class MachXO(model.Target, memory.Loadable):
    """
    Mach-XO2 target
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        memory.Loadable.__init__(self)
        self.child_add(MachConfig(comp))
        self.child_add(MachFeature(comp))
        self.child_add(MachFlash(comp))
        if comp.info.ufm_page_count:
            self.child_add(MachUfm(comp))
        self.component = comp

    def erase_all(self):
        self.component.stop()
        self.component.erase_all()
        self.force_blank()

    def reset(self):
        self.component.reset()
