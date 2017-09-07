from . import model
from ..component import spi_flash as component_spi_flash
from . import memory

__all__ = ["SpiFlash"]

class Bank(memory.NandFlash):
    def __init__(self, flash):
        memory.NandFlash.__init__(self, flash.name + " data", 0, flash.total_size, flash.page_size)
        self.flash = flash

    def erase(self, offset, size):
        assert 0 <= offset < size
        assert 0 <= offset + size <= size

        if size == self.size:
            self.flash.erase_all()
            self.blank = True
        else:
            self.flash.erase(offset, size)

    def write(self, offset, data):
        self.flash.write(offset, data)
        self.blank = False

    def read(self, offset, size):
        return self.flash.read(offset, size)

@model.Target.register(component_spi_flash.SpiFlash)
class SpiFlash(model.Target, memory.Loadable):
    """
    A SPI flash
    """

    def __init__(self, comp):
        model.Target.__init__(self, comp.name)
        memory.Loadable.__init__(self)
        self.child_add(Bank(comp))
        self.component = comp

    def erase_all(self):
        self.component.erase_all()
        self.force_blank()
