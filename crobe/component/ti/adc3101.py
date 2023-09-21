from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *

class ADC3101(i2c.Slave):
    def __init__(self, bus, saddr):
        super().__init__(bus, "adc3101", saddr)
        self.page = None

    def page_switch(self, page):
        if page == self.page:
            return

        self.page = page
        self.logger.trace("Page switch %#04x", page)
        self.write(bytes([0, page]))

    def reg_read(self, reg):
        reg = int(reg)

        addr = reg & 0xff
        self.page_switch(reg >> 8)

        value, = self.write_read(addr, 1)

        self.logger.trace("Reg read %#04x %#04x", reg, value)

        return value

    def reg_write(self, reg, value):
        reg = int(reg)

        addr = reg & 0xff
        self.page_switch(reg >> 8)

        self.logger.trace("Reg write %#04x %#04x", reg, value)
        self.write(bytes([addr, value]))

@i2c.Interface.db.register("adc3101")
def adc3101_get(bus):
    return ADC3101(bus, None)
