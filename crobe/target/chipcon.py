from . import model
from ..component.ti.cc_8051 import CC_8051
from . import memory

__all__ = ["CC"]

class CCFlash(memory.Flash):
    def __init__(self, cc):
        memory.Flash.__init__(self, "flash", 0, cc.flash_size, cc.info.page_size)
        self.cc = cc

    def erase(self, offset, size):
        for addr in range(offset & ~(self.cc.info.page_size - 1),
                          offset + size,
                          self.cc.info.page_size):
            self.logger.trace("Erasing page at 0x%05x", offset)
            self.cc.flash_page_erase(addr)

    def write(self, offset, data):
        self.logger.trace("Writing page at 0x%05x", offset)
        self.cc.flash_write(offset, data)

    def read(self, offset, size):
        self.logger.trace("Reading %d bytes at 0x%05x", size, offset)
        start = offset & ~(self.cc.info.page_size - 1)
        data = b""
        for addr in range(start, offset + size, self.cc.info.page_size):
            c = self.cc.cmd_flash_read(addr, self.cc.info.page_size)
            self.cc.port.execute([c])
            data += c.data
        return data[offset - start : offset - start + size]

class CCRam(memory.Ram):
    def __init__(self, cc):
        memory.Ram.__init__(self, "ram", 0, cc.ram_size)
        self.cc = cc

@model.Target.register(CC_8051)
class CCFlashTarget(model.Target, memory.Loadable):
    """
    A Chipcon CC2xxx flash
    """

    def __init__(self, comp):
        model.Target.__init__(self, "CC Flash for " + comp.name)
        memory.Loadable.__init__(self)
        self.flash = CCFlash(comp)
        self.child_add(self.flash)
        self.child_add(CCRam(comp))
        self.component = comp

    def erase_all(self):
        self.component.port.execute([self.component.cmd_mass_erase()])

    def write(self, program):
        for r in self.children:
            blank = r.is_blank

            pages = program.within(self.flash.address, self.flash.address + self.flash.size)

            for page in pages.paged(self.flash.page_size, fill = b'\xff'):
                self.flash.erase(page.address - self.flash.address, self.flash.page_size)
                self.flash.write(page.address - self.flash.address, page.data)
