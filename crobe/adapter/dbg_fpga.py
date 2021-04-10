from . import model
from ..protocol import i2c, spi, swd, jtag, base
from .. import bitstring
from ..util.pretty import metric
from ..util import endian
from ..db import NoMatch
from collections import deque
import usb.core
import usb.util
import binascii
import time
import os
import math
import struct
import threading
from ..component.nsl.transactor.cs import ControlStatus

__all__ = []

class BackgroundWriter(threading.Thread):
    def __init__(self, adapter, ep, data, timeout):
        threading.Thread.__init__(self)
        self.adapter = adapter
        self.ep = ep
        self.data = data
        self.timeout = timeout

    def run(self):
        self.adapter.bulk_out(self.ep, self.data, int(self.timeout * 1000))
        
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1500, idProduct = 0xdeb9))
class Adapter(model.Adapter):
    EP_IN  = 0x81
    EP_OUT = 0x01
    supported_interfaces = ["spi"]

    def bulk_out(self, data, timeout = None):
        self.logger.debug("BULK OUT %s", binascii.b2a_hex(data))
        self.device.write(self.EP_OUT, data, int((timeout or 1.) * 1000))

    def bulk_in(self, size, timeout = None):
        self.logger.debug("BULK IN %d", size)
        data = self.device.read(self.EP_IN, size, int((timeout or 1.) * 1000))
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def execute(self, blob, read_size = 0):
        self.logger.debug("Execute, %d out, %d in", len(blob), read_size)
        self.bulk_out(blob)
        rbuf = b''
        while len(rbuf) < read_size:
            rbuf += self.bulk_in(512)
        return rbuf

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "df-%s" % (serial,))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device

    def open(self, interface_name):
        try:
            self.execute(b"\x07", 64, timeout = .05)
        except:
            pass
        if interface_name.lower() == "spi":
            return BlSpiInterface(self)

class BlSpiInterface(spi.Interface):
    def __init__(self, port):
        from ..component.nsl.transactor.spi import SpiTransactor
        self.transactor = None
        spi.Interface.__init__(self, port)
        self.transactor = SpiTransactor(port, 60e6)

        self.child_add(spi.Target(self, "cs0", 0))
        self.child_add(spi.Target(self, "cs1", 1))

    def freq_update(self, freq):
        print("freq_update", freq, self.transactor)
        if self.transactor is None:
            return 1
        return self.transactor.freq_update(freq)

    def execute(self, operation_list):
        return self.transactor.execute(operation_list)

class Registers(ControlStatus):
    REG_V = 0
    REG_I = 1
    REG_APP_CLK = 2
    REG_MODE = 3
    REG_IO = 4

    def reg_update(self, id, mask, new_value):
        old = self.reg_read(id)
        new = (old & ~mask) | (new_value & mask)
        self.logger.debug("RMW %d: 0x%08x + (0x%08x &  0x%08x) ->  0x%08x",
                          id, old, mask, new_value, new)
        self.reg_write(id, new)

    def target_voltage_set(self, supply = False, voltage = None):
        mask = 0x0003f003
        value = 0
        assert not supply or voltage is not None
        if voltage is not None:
            value |= int(voltage * 16) << 12
        else:
            value |= 2 # track
        if supply:
            value |= 1
        self.reg_update(self.REG_V, mask, value)

    def mode_set(self, mode = "NONE"):
        if mode == "NONE":
            m = 0x0
        elif mode == "JTAG":
            m = 0x1
        elif mode == "SWD":
            m = 0x2
        elif mode == "SPI":
            m = 0x3
        elif mode == "SPI-INV":
            m = 0x4
        elif mode == "I2C-INT":
            m = 0x5
        elif mode == "I2C-EXT":
            m = 0x6
        elif mode == "I2C-TGT":
            m = 0x7
        elif mode == "FORCE":
            m = 0x1f
        else:
            try:
                m = int(mode)
            except:
                m = 0
        self.reg_update(self.REG_MODE, 0x1f, m)

    def reset_assert(self, asserted):
        self.logger.info("%s reset", "Holding" if asserted else "Releasing")
        self.reg_update(self.REG_MODE, 0x10, -int(bool(asserted)))

    def target_voltage_get(self):
        reg = self.reg_read(self.REG_V)
        xadc_v = ((reg >> 4) & 0xfff) / (1 << 12)
        vtarget = xadc_v * 10
        return vtarget

    def target_current_get(self):
        reg = self.reg_read(self.REG_I)
        xadc_v = ((reg >> 4) & 0xfff) / (1 << 12)
        itarget = xadc_v * .125
        return itarget

    def is_over_current(self):
        reg = self.reg_read(self.REG_I)
        return bool(reg & 1)

    def base_freq(self):
        return self.reg_read(self.REG_APP_CLK)

class DbgFpgaVoltage:
    def __init__(self, regs):
        self.regs = regs
        self.cycle = False
        self.power = "track", None

    def option_set(self, value):
        if value.startswith("poweroff"):
            self.cycle = True
            return True
        if value.startswith("vsupply="):
            self.power = "supply", float(value[8:])
            return True
        if value.startswith("vref="):
            self.power = "force", float(value[5:])
            return True

    def apply(self):
        if self.cycle:
            self.regs.logger.info("Cycling target")
            self.regs.target_voltage_set(supply = True, voltage = 0)
            time.sleep(.2)

        mode, value = self.power
        if mode == "track":
            self.regs.logger.info("Tracking target voltage")
            self.regs.target_voltage_set()
        elif mode == "supply":
            self.regs.logger.info("Setting target voltage as %1.1fV", value)
            self.regs.target_voltage_set(supply = True, voltage = value+.025)
        else:
            self.regs.logger.info("Setting reference voltage to %1.1fV", value)
            self.regs.target_voltage_set(voltage = value+.025)
        time.sleep(.2)
        self.regs.logger.info("Current target voltage: %1.3f", self.regs.target_voltage_get())

class I2cInterface(i2c.Interface):
    def __init__(self, framed_i2c, base_freq, regs):
        from crobe.component.nsl.transactor.i2c import I2cTransactor
        self.__i2c_trx = I2cTransactor(framed_i2c, base_freq)
        super().__init__(self.__i2c_trx, "i2c")
        self.child_add(self.__i2c_trx)
        self.voltage = DbgFpgaVoltage(regs)

    def execute(self, op_list):
        self.logger.info(op_list)
        self.__i2c_trx.execute(op_list)

    def freq_update(self, freq):
        return self.__i2c_trx.freq_update(freq)

    def option_set(self, opt):
        if self.voltage.option_set(opt):
            return
        super().option_set(opt)

class SwdInterface(swd.Interface):
    def __init__(self, framed_swd, base_freq, regs):
        from crobe.component.nsl.transactor.swd import SwdTransactor
        self.swd = SwdTransactor(framed_swd, base_freq)
        super().__init__(self.swd, "swd")
        self.voltage = DbgFpgaVoltage(regs)

    def start(self):
        self.voltage.apply()
        super().start()

    def option_set(self, opt):
        if self.voltage.option_set(opt):
            return
        super().option_set(opt)
        
    @property
    def turnaround_cycles(self):
        return self.swd.turnaround_cycles

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        self.swd.turnaround_cycles = cycles

    def execute(self, op_list):
        self.swd.execute(op_list)

    def freq_update(self, freq):
        return self.swd.freq_update(freq)

class JtagInterface(jtag.Interface):
    def __init__(self, framed_jtag, base_freq, regs):
        from crobe.component.nsl.transactor.jtag import JtagTransactor
        self.jtag = JtagTransactor(framed_jtag, base_freq)
        super().__init__(self.jtag, "jtag")
        self.voltage = DbgFpgaVoltage(regs)

    def start(self):
        self.voltage.apply()
        super().start()

    def option_set(self, opt):
        if self.voltage.option_set(opt):
            return
        super().option_set(opt)

    def execute(self, op_list):
        self.jtag.execute(op_list)

    def freq_update(self, freq):
        return self.jtag.freq_update(freq)

class SpiInterface(spi.Interface):
    def __init__(self, framed_spi, base_freq, regs):
        from crobe.component.nsl.transactor.spi import SpiTransactor
        self.regs = regs
        self.spi = SpiTransactor(framed_spi, base_freq)
        super().__init__(self.spi, "spi")
        self.voltage = DbgFpgaVoltage(regs)
        self.child_add(spi.Target(self, "cs0", 0))

    def start(self):
        self.voltage.apply()
        super().start()

    def option_set(self, opt):
        if self.voltage.option_set(opt):
            return
        super().option_set(opt)

    def reset_assert(self, asserted):
        self.regs.reset_assert(asserted)
        
    def execute(self, op_list):
        todo = []
        for o in op_list:
            if isinstance(o, base.Reset):
                if todo:
                    self.spi.execute(todo)
                todo = []
                self.reset_assert(o.asserted)
            else:
                todo.append(o)
        if todo:
            self.spi.execute(todo)

    def freq_update(self, freq):
        return self.spi.freq_update(freq)
    
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1500, idProduct = 0xdeba))
class Adapter(model.Adapter):
    EP_IN  = 0x81
    EP_OUT = 0x01
    supported_interfaces = ["cs", "jtag", "swd", "spi", "spi-inv", "i2c", "i2c-int", "i2c-ext"]

    def bulk_out(self, data, timeout = None):
        self.logger.debug("BULK OUT %s", binascii.b2a_hex(data))
        self.device.write(self.EP_OUT, data, int((timeout or 1.) * 1000))

    def bulk_in(self, size, timeout = None):
        self.logger.debug("BULK IN %d", size)
        data = self.device.read(self.EP_IN, size, int((timeout or 1.) * 1000))
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def execute(self, blob, read_size = 0):
        self.logger.debug("Execute, %d out, %d in", len(blob), read_size)
        self.bulk_out(blob)
        rbuf = b''
        while len(rbuf) < read_size:
            rbuf += self.bulk_in(512)
        return rbuf

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "df-%s" % (serial,))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device

        cfg = self.device.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.device.set_configuration(1)
            cfg = self.device.get_active_configuration()

    def write(self, data):
        self.bulk_out(data)

    def _read(self):
        return self.bulk_in(512)
        
    def open(self, interface_name):
        from ..component.nsl.bnoc.routed import Router
        from ..component.nsl.bnoc.sized import Sized

        s = Sized(self)
        r = Router(s)
        self.regs = Registers(r.route(0xf, 0x0).framed_endpoint())
        self.child_add(self.regs)
        self.base_freq = self.regs.base_freq()

        self.swd = SwdInterface(r.route(0xf, 0x1).framed_endpoint(), self.base_freq, self.regs)
        self.jtag = JtagInterface(r.route(0xf, 0x2).framed_endpoint(), self.base_freq, self.regs)
        self.spi = SpiInterface(r.route(0xf, 0x3).framed_endpoint(), self.base_freq, self.regs)
        self.i2c = I2cInterface(r.route(0xf, 0x4).framed_endpoint(), self.base_freq, self.regs)

        self.child_add(self.jtag)
        self.child_add(self.spi)
        self.child_add(self.swd)
        self.child_add(self.i2c)

        if interface_name.lower() == "cs":
            return self.regs

        elif interface_name.lower() == "jtag":
            self.regs.mode_set("JTAG")
            return self.jtag

        elif interface_name.lower() == "spi":
            self.regs.mode_set("SPI")
            return self.spi

        elif interface_name.lower() == "spi-inv":
            self.regs.mode_set("SPI-INV")
            return self.spi

        elif interface_name.lower() == "swd":
            self.regs.mode_set("SWD")
            return self.swd

        elif interface_name.lower() == "i2c":
            self.regs.mode_set("I2C-TGT")
            return self.i2c

        elif interface_name.lower() == "i2c-ext":
            self.regs.mode_set("I2C-EXT")
            return self.i2c

        elif interface_name.lower() == "i2c-int":
            self.regs.mode_set("I2C-INT")
            return self.i2c
