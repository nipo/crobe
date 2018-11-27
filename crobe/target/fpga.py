from . import model
from ..component.xilinx.spartan6 import Spartan6
from ..component.xilinx.zynq import Zynq
from ..component.lattice.mach import MachXO2Config
from . import memory
import time

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
        self.fpga._config_write(data)

class MachFlash(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "flash", 0x20000000, fpga.info.flash_page_count * 16)

    def erase(self, offset, size):
        if offset:
            raise NotImplementedError()
        self.fpga.flash_erase()

    def write(self, offset, data):
        self.fpga._flash_write(offset, data)

    def read(self, offset, length):
        return self.fpga._flash_read(offset, length)

class MachUfm(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "ufm", 0x20000000 + fpga.info.flash_page_count * 16, fpga.info.ufm_page_count * 16)

    def erase(self, offset, size):
        if offset == 0:
            self.fpga.ufm_erase()

    def write(self, offset, data):
        self.fpga._ufm_write(offset, data)

    def read(self, offset, length):
        return self.fpga._ufm_read(offset, length)

class MachFea(MachMem):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.PARTIAL_READ, memory.Flag.MM_READ])

    def __init__(self, fpga):
        MachMem.__init__(self, fpga, "Feature/Feabits", 0x10000000, 10)

    def erase(self, offset, size):
        self.fpga._feature_erase()

    def read(self, offset, length):
        assert offset == 0 and length == 10
        return self.fpga._feature_read() + self.fpga._feabits_read()

    def write(self, offset, data):
        assert offset == 0 and len(data) == 10
        self.fpga._feature_write(data[:8])
        self.fpga._feabits_write(data[8:])

@model.Target.register(MachXO2Config)
class MachXO(model.Target, memory.Loadable):
    """
    Mach-XO2 target
    """

    def __init__(self, comp):
        model.Target.__init__(self, "FPGA: " + comp.name)
        memory.Loadable.__init__(self)
        self.child_add(MachConfig(comp))
        self.child_add(MachFlash(comp))
        if comp.info.ufm_page_count:
            self.child_add(MachUfm(comp))
        self.child_add(MachFea(comp))
        self.component = comp

    def program_begin(self, do_erase = False):
        if not do_erase:
            raise NotImplementedError("Cannot program FPGA without erasing")
        self.component._isc_enable(False)
        memory.Loadable.program_begin(self, do_erase)
        self.component._stop()
        self.component._isc_enable(False)

    def attach(self):
        self.component._isc_enable(False)

    def erase_all(self):
        self.component._erase_all()
        self.force_blank()

    def reset(self):
        self.component.reset()

    def program_end(self, success, do_start):
        self.component._usercode_write(0)

        memory.Loadable.program_end(self, success, do_start = False)
        self.component._flash_done_set()
        time.sleep(.5)

        assert self.component.done

        self.component._isc_disable()
        time.sleep(.1)
        self.component._bypass()
        time.sleep(.1)

        if do_start:
            self.component._refresh()
            time.sleep(.1)

        if do_start:
            self.component._assert_done()
