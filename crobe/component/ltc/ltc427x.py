from ...model import PortComponent
from ...protocol import i2c
from .ltc4266 import Ltc4266
import struct

@i2c.Interface.db.register("ltc427x")
class Ltc427x(PortComponent):
    def __init__(self, bus, saddr = None):
        PortComponent.__init__(self, bus, "LTC427x")
        self.low = Ltc4266(bus, saddr if saddr else None)
        self.high = Ltc4266(bus, saddr + 1 if saddr else None)
        self.port_count = 8

    def option_set(self, opt):
        k, v = opt.split('=', 1)

        if k == 'saddr':
            self.low.saddr = int(v, 16)
            self.high.saddr = int(v, 16)+1
        else:
            return PortComponent.option_set(opt)

    def port_status_get(self, no):
        if no < 4:
            return self.low.port_status_get(no)
        return self.high.port_status_get(no - 4)

    def port_current_get(self, no):
        if no < 4:
            return self.low.port_current_get(no)
        return self.high.port_current_get(no - 4)

    def port_voltage_get(self, no):
        if no < 4:
            return self.low.port_voltage_get(no)
        return self.high.port_voltage_get(no - 4)

    def port_disable(self, no):
        if no < 4:
            return self.low.port_disable(no)
        return self.high.port_disable(no - 4)

    def port_enable(self, no):
        if no < 4:
            return self.low.port_enable(no)
        return self.high.port_enable(no - 4)

    def port_auto_enable(self, no):
        if no < 4:
            return self.low.port_auto_enable(no)
        return self.high.port_auto_enable(no - 4)
