from . import model
from ..component import spi_flash as component_spi_flash
from . import loadable

__all__ = ["SpiFlash"]

@model.Target.register(component_spi_flash.SpiFlash)
class SpiFlash(model.Target, loadable.Loadable):
    """
    A SPI flash
    """

    def __init__(self, comp):
        model.Target.__init__(self, comp.name)
        self.component = comp
    
    def read(self, address, size):
        return self.component.read(addres, size)

    def erase_all(self):
        return self.component.erase_all()

    def write(self, program, erase_first = True, verify = False):
        return self.component.write(program, erase_first = erase_first, verify = verify)

    def verify(self, program):
        return self.component.verify(program)

