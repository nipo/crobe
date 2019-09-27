from crobe.model import PortComponent
from ...protocol import i2c
import struct

@i2c.Interface.db.register("ltc4266")
class Ltc4266(PortComponent):
    def __init__(self, bus, saddr = None):
        PortComponent.__init__(self, bus, "LTC4266")
        self.saddr = saddr
        self.port_count = 4

    def option_set(self, opt):
        k, v = opt.split('=', 1)

        if k == 'saddr':
            self.saddr = int(v, 16)
            self.logger.debug("Slave addr now %02x", self.saddr)
        else:
            return PortComponent.option_set(opt)

    def reg8_read(self, reg):
        rdata = self.port.write_read(self.saddr, bytes([reg]), 1)
        return rdata[0]

    def reg8_write(self, reg, value):
        self.port.write(self.saddr, bytes([reg, value]))

    def reg16_read(self, reg):
        rdata = self.port.write_read(self.saddr, bytes([reg]), 2)
        return int.from_bytes(rdata, "little")

    def reg16_write(self, reg, value):
        self.port.write(self.saddr, bytes([reg, value & 0xff, value >> 8]))

    PORT_STATE_ADDR = 0x0c
    PORT_STATE = {0:"Unknown", 1: "Short", 2: "CPD Too high", 3: "Low",
                  4: "Good", 5: "High", 6: "Open", 7: "Reserved"}
    PORT_CLASS = {0:"Unknown", 1:"Class 1", 2:"Class 2", 3:"Class 3",
                  4: "Class 4", 6: "Class 0"}

    def port_status_get(self, no):
        v = self.reg8_read(self.PORT_STATE_ADDR + no)
        state = self.PORT_STATE.get(v & 0x7, "?")
        clas = self.PORT_CLASS.get(v >> 4, "?")

        return clas, state

    PORT_CURRENT_ADDR = 0x30

    def port_current_get(self, no):
        v = self.reg16_read(self.PORT_CURRENT_ADDR + no * 4)
        return v * .00012208

    PORT_VOLTAGE_ADDR = 0x32

    def port_voltage_get(self, no):
        v = self.reg16_read(self.PORT_VOLTAGE_ADDR + no * 4)
        return v * 0.005844

    DETECT_ENABLE_ADDR = 0x14
    DETECT_CONTROL_ADDR = 0x18
    POWER_CONTROL_ADDR = 0x19

    def port_disable(self, no):
        self.reg8_write(self.POWER_CONTROL_ADDR, 1 << (4 + no))

    def port_enable(self, no):
        self.reg8_write(self.POWER_CONTROL_ADDR, 1 << no)

    def port_auto_enable(self, no):
        self.reg8_write(self.DETECT_ENABLE_ADDR, (0x11 << no) | self.reg8_read(self.DETECT_ENABLE_ADDR))
