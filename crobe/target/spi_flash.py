from . import model
from ..component import spi_flash as component_spi_flash
from . import memory

__all__ = ["SpiFlash"]

class Bank(memory.NandFlash):
    def __init__(self, flash):
        memory.NandFlash.__init__(self, flash.name + " data", 0, flash.total_size, 4096)
        self.flash = flash

    def erase(self, offset, size):
        if not size:
            return

        assert 0 <= offset < self.size, (offset, size, self.size)
        assert 0 <= offset + size <= self.size, (offset, size, self.size)

        if size == self.size:
            self.flash.erase_all()
            self.blank = True
        else:
            self.flash.erase(offset, size)

    def write(self, offset, data):
        off = 0

        while off < len(data):
            alignment = (offset + off) % self.page_size
            size = self.page_size - alignment

            chunk = data[off : off + size]

            self.flash.write(offset + off, chunk)
            self.blank = False

            off += len(chunk)

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
