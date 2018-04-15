from . import model
from ..component import i2c_eeprom as component_i2c_eeprom
from . import memory

__all__ = ["I2cEeprom"]

class Bank(memory.Eeprom):
    def __init__(self, eeprom):
        memory.Eeprom.__init__(self, eeprom.name + " data", 0, eeprom.size)
        self.eeprom = eeprom

    def write(self, offset, data):
        self.eeprom.write(offset, data)

    def read(self, offset, size):
        return self.eeprom.read(offset, size)

@model.Target.register(component_i2c_eeprom.I2cEeprom)
class I2cEeprom(model.Target, memory.Loadable):
    """
    An I2C eeprom
    """

    def __init__(self, comp):
        model.Target.__init__(self, comp.name)
        memory.Loadable.__init__(self)
        self.child_add(Bank(comp))
        self.component = comp

    def erase_all(self):
        pass
