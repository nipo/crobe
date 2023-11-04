from . import model
from ..protocol import i2c, spi, swd, jtag, base, bitbang
from .. import bitstring
from ..util.pretty import metric, sci_parse
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
import enum
from ..component.nsl.transactor.cs import ControlStatus
import enum

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

class Mode(enum.IntEnum):
    NONE    = 0
    JTAG    = 1
    SWD     = 2
    SPI     = 3
    SPI_INV = 4
    I2C_INT = 5
    I2C_EXT = 6
    I2C_TGT = 7
    SWD_EXT = 8
    JTAG_EXT = 9
    SPI_SLAVE = 10
    SPI_SLAVE_INV = 11
        
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1500, idProduct = 0xdeb9))
class Adapter(model.Adapter):
    """
    dbg-fpga board firmware bootloader, only defines SPI transactor to the bitstream flash
    """
    EP_IN  = 0x81
    EP_OUT = 0x01
    supported_interfaces = ["spi"]

    def bulk_out(self, data, timeout = None):
        self.logger.protocol("BULK OUT %s", binascii.b2a_hex(data))
        self.handle.write(self.EP_OUT, data, int((timeout or 1.) * 1000))

    def bulk_in(self, size, timeout = None):
        self.logger.protocol("BULK IN %d", size)
        data = self.handle.read(self.EP_IN, size, int((timeout or 1.) * 1000))
        self.logger.protocol("-> %s", binascii.b2a_hex(data))
        return data

    def execute(self, blob, read_size = 0):
        self.logger.trace("Execute, %d out, %d in", len(blob), read_size)
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
        self.handle = device
        self.io = None

    def _open(self):
        if self.io:
            return
        cfg = self.handle.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.handle.set_configuration(1)
            cfg = self.handle.get_active_configuration()
        for intf in cfg:
            self.logger.debug("Has interface %d, %02x:%02x:%02x",
                  intf.index,
                  intf.bInterfaceClass,
                  intf.bInterfaceSubClass,
                  intf.bInterfaceProtocol)
            if intf.bInterfaceClass == 0xff and \
               intf.bInterfaceSubClass == 0xff and \
               intf.bInterfaceProtocol == 0xff:
                self.intf = intf
                break
        usb.util.claim_interface(self.handle, self.intf)

        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)

        self.logger.debug("Using interface %d, EP_IN: %02x, EP_OUT: %02x",
                          self.intf.index,
                          self.ep_in.bEndpointAddress,
                          self.ep_out.bEndpointAddress)

        self.io = model.BulkStreamPair(self, self.handle, "io", self.ep_out, self.ep_in)
        self.child_add(self.io)

    def open(self, interface_name):
        self._open()
        try:
            self.execute(b"\x07", 64, timeout = .05)
        except:
            pass
        if interface_name.lower() == "spi":
            return BlSpiInterface(self.io)

class BlSpiInterface(spi.Interface):
    def __init__(self, port):
        from ..component.nsl.transactor.spi import SpiTransactor
        self.transactor = None
        spi.Interface.__init__(self, port)
        self.transactor = SpiTransactor(port, 60e6)

        self.child_add(spi.Target(self, "cs0", 0))
        self.child_add(spi.Target(self, "cs1", 1))

    def freq_update(self, freq):
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
    REG_BAUDRATE = 5

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

    def mode_set(self, mode = Mode.NONE):
        m = int(mode)
        self.reg_update(self.REG_MODE, 0x1f, m)

    def reset_assert(self, asserted):
        self.logger.trace("%s reset", "Holding" if asserted else "Releasing")
        self.reg_update(self.REG_MODE, 0x20000, -int(bool(asserted)))

    def detect_assert(self, asserted):
        self.logger.trace("%s detect", "Holding" if asserted else "Releasing")
        self.reg_update(self.REG_MODE, 0x10000, -int(not asserted))

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

    def baudrate_set(self, rate):
        app_clk = self.reg_read(self.REG_APP_CLK)
        divisor = int(app_clk / rate) - 1
        self.reg_write(self.REG_BAUDRATE, divisor)

    def baudrate_get(self):
        app_clk = self.reg_read(self.REG_APP_CLK)
        divisor = self.reg_read(self.REG_BAUDRATE) + 1
        return int(app_clk / divisor)

class DbgFpgaOpts:
    def __init__(self, regs):
        self.regs = regs
        self.cycle_time = 0
        self.power = "track", None
        self.power_settle = .2
        self.baudrate = None
        self.detect = True

    def option_set(self, value):
        if value.startswith("baudrate="):
            self.baudrate = sci_parse(value[9:])
            return True
        if value.startswith("poweroff"):
            self.cycle_time = .2
            if value.startswith("poweroff="):
                self.cycle_time = float(value[9:])
            return True
        if value.startswith("vsupply="):
            self.power = "supply", float(value[8:])
            return True
        if value.startswith("vref="):
            self.power = "force", float(value[5:])
            return True
        if value.startswith("power_settle="):
            self.power_settle = float(value[13:])
            return True
        if value.startswith("nodetect"):
            self.detect = False
            return True

    def apply(self):
        self.regs.detect_assert(self.detect)
        if self.baudrate is not None:
            self.regs.baudrate_set(self.baudrate)
            br = self.regs.baudrate_get()
            self.regs.logger.note("Setting baud rate to %s, got %s",
                                  metric(self.baudrate, "baud"),
                                  metric(br, "baud"))

        if self.cycle_time:
            self.regs.logger.note("Cycling target")
            self.regs.target_voltage_set(supply = True, voltage = 0)
            time.sleep(self.cycle_time)

        mode, value = self.power
        if mode == "track":
            self.regs.logger.note("Tracking target voltage")
            self.regs.target_voltage_set()
        elif mode == "supply":
            self.regs.logger.note("Setting target voltage as %1.1fV", value)
            self.regs.target_voltage_set(supply = True, voltage = value+.025)
        else:
            self.regs.logger.note("Setting reference voltage to %1.1fV", value)
            self.regs.target_voltage_set(voltage = value+.025)
        time.sleep(self.power_settle)
        target_voltage = self.regs.target_voltage_get()
        self.regs.logger.info("Current target voltage: %1.3f", target_voltage)
        if mode == "track" and target_voltage < 0.5:
            raise base.TargetError("No target VCC detected")

class I2cInterface(i2c.Interface):
    def __init__(self, framed_i2c, base_freq, regs):
        from ..component.nsl.transactor.i2c import I2cTransactor
        self.__i2c_trx = I2cTransactor(framed_i2c, base_freq)
        super().__init__(self.__i2c_trx, "i2c")
        self.child_add(self.__i2c_trx)
        self.options = DbgFpgaOpts(regs)

    def execute(self, op_list):
        self.logger.protocol("%s", op_list)
        self.__i2c_trx.execute(op_list)

    def freq_update(self, freq):
        return self.__i2c_trx.freq_update(freq)

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
            return
        super().option_set(opt)

class SwdInterface(swd.Interface):
    def __init__(self, framed_swd, base_freq, regs):
        from ..component.nsl.transactor.swd import SwdTransactor
        self.swd = SwdTransactor(framed_swd, base_freq)
        super().__init__(self.swd, "swd")
        self.options = DbgFpgaOpts(regs)

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
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
        from ..component.nsl.transactor.jtag import JtagTransactor
        self.jtag = JtagTransactor(framed_jtag, base_freq)
        super().__init__(self.jtag, "jtag")
        self.options = DbgFpgaOpts(regs)

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
            return
        super().option_set(opt)

    def execute(self, op_list):
        self.jtag.execute(op_list)

    def freq_update(self, freq):
        return self.jtag.freq_update(freq)

class SpiInterface(spi.Interface):
    def __init__(self, framed_spi, base_freq, regs):
        from ..component.nsl.transactor.spi import SpiTransactor
        self.regs = regs
        self.spi = SpiTransactor(framed_spi, base_freq)
        super().__init__(self.spi, "spi")
        self.options = DbgFpgaOpts(regs)
        self.child_add(spi.Target(self, "cs0", 0))

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
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

class NoneInterface(base.Interface):
    def __init__(self, regs):
        self.regs = regs
        self.options = DbgFpgaOpts(regs)
        self.options.detect = False
        super().__init__(regs, "none")

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
            return
        super().option_set(opt)

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1500, idProduct = 0xdeba, bcdDevice = 0x0100))
class Adapter(model.Adapter):
    """
    "target_cortex0" target board multi-protocol firmware, rev 1.00, has most serial protocol transactors
    """
    supported_interfaces = ["cs", "jtag", "swd", "spi", "spi-inv", "i2c", "i2c-int", "i2c-ext", 'bb']

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "df-%s" % (serial,))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.handle = device
        self.io = None

    def _open(self):
        from ..component.nsl.bnoc.routed import Router
        from ..component.nsl.bnoc.sized import Sized

        if self.io:
            return

        cfg = self.handle.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.handle.set_configuration(1)
            cfg = self.handle.get_active_configuration()
        for intf in cfg:
            self.logger.debug("Has interface %d, %02x:%02x:%02x",
                  intf.index,
                  intf.bInterfaceClass,
                  intf.bInterfaceSubClass,
                  intf.bInterfaceProtocol)
            if intf.bInterfaceClass == 0xff and \
               intf.bInterfaceSubClass == 0xff and \
               intf.bInterfaceProtocol == 0xff:
                self.intf = intf
                break
        usb.util.claim_interface(self.handle, self.intf)

        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)

        self.logger.debug("Using interface %d, EP_IN: %02x, EP_OUT: %02x",
                          self.intf.index,
                          self.ep_in.bEndpointAddress,
                          self.ep_out.bEndpointAddress)

        self.io = model.BulkStreamPair(self, self.handle, "io", self.ep_out, self.ep_in)
        self.child_add(self.io)
        
        s = Sized(self.io)
        self.child_add(s)
        r = Router(s)
        self.child_add(r)

        self.regs = Registers(r.route(0xf, 0x0).framed_endpoint())
        self.child_add(self.regs)
        self.base_freq = self.regs.base_freq()

        self.swd = SwdInterface(r.route(0xf, 0x1).framed_endpoint(), self.base_freq, self.regs)
        self.jtag = JtagInterface(r.route(0xf, 0x2).framed_endpoint(), self.base_freq, self.regs)
        self.spi = SpiInterface(r.route(0xf, 0x3).framed_endpoint(), self.base_freq, self.regs)
        self.i2c = I2cInterface(r.route(0xf, 0x4).framed_endpoint(), self.base_freq, self.regs)
        self.none = NoneInterface(self.regs)

        self.child_add(self.jtag)
        self.child_add(self.spi)
        self.child_add(self.swd)
        self.child_add(self.i2c)

    def open(self, interface_name):
        self._open()

        if interface_name.lower() == "cs":
            return self.regs

        elif interface_name.lower() == "jtag":
            self.regs.mode_set(Mode.JTAG)
            return self.jtag

        elif interface_name.lower() == "spi":
            self.regs.mode_set(Mode.SPI)
            return self.spi

        elif interface_name.lower() == "spi-inv":
            self.regs.mode_set(Mode.SPI_INV)
            return self.spi

        elif interface_name.lower() == "swd":
            self.regs.mode_set(Mode.SWD)
            return self.swd

        elif interface_name.lower() == "i2c":
            self.regs.mode_set(Mode.I2C_TGT)
            return self.i2c

        elif interface_name.lower() == "i2c-ext":
            self.regs.mode_set(Mode.I2C_EXT)
            return self.i2c

        elif interface_name.lower() == "i2c-int":
            self.regs.mode_set(Mode.I2C_INT)
            return self.i2c

        elif interface_name.lower() == "none":
            self.regs.mode_set(Mode.NONE)
            return self.none

class DbgFpgaIoInfo(bitbang.IoInfo):
    def __init__(self, name, no, opendrain):
        self.name = name
        self.no = no
        self.opendrain = opendrain
        
class BitbangInterface(bitbang.Interface):
    def __init__(self, adapter):
        self.options = DbgFpgaOpts(adapter.regs)
        self.options.detect = False
        super().__init__(adapter.regs, "BB")
        self.adapter = adapter
        self.out_reg = 0
        self.repeats = 1

    def start(self):
        self.options.apply()
        super().start()

    def option_set(self, opt):
        if self.options.option_set(opt):
            return
        super().option_set(opt)

    _ios = {x.name:x for x in [
        DbgFpgaIoInfo("target_tdo", 0, False),
        DbgFpgaIoInfo("target_tck", 1, False),
        DbgFpgaIoInfo("target_tms", 2, False),
        DbgFpgaIoInfo("target_tdi", 3, False),
        DbgFpgaIoInfo("ext0", 4, False),
        DbgFpgaIoInfo("ext1", 5, False),
        DbgFpgaIoInfo("ext2", 6, False),
        DbgFpgaIoInfo("ext3", 7, False),
        DbgFpgaIoInfo("ext4", 8, False),
        DbgFpgaIoInfo("ext5", 9, False),
        DbgFpgaIoInfo("target_resetn", 10, True),
    ]}
        
    def io_info(self):
        return self._ios

    def freq_update(self, freq):
        base = 60e6/5
        if not freq:
            self.repeats = 1
            return base
        repeats = base / freq
        self.repeats = int(math.ceil(repeats)) or 1
        return base / repeats

    def _execute(self, operation_list):
        pending = []
        ridx = {}

        for op in operation_list:
            if isinstance(op, bitbang.IoSet):
                for iop in op.ops:
                    io = self._ios[iop.io]

                    m = 1 << io.no
                    oe = 1 << (io.no + 16)

                    if iop.mode is not None:
                        io.mode = iop.mode

                    if (io.mode & bitbang.Mode.D1) and iop.value and (not io.opendrain):
                        self.out_reg |= oe | m
                    elif (io.mode & bitbang.Mode.D0) and (not iop.value) and (iop.value is not None):
                        self.out_reg |= oe
                        self.out_reg &= ~m
                    else:
                        self.out_reg &= ~(oe | m)
                pending += [self.port.cmd_reg_write(self.port.REG_IO, self.out_reg)] * self.repeats

            elif isinstance(op, bitbang.IoGet):
                ridx[op] = len(pending)
                pending.append(self.port.cmd_reg_read(self.port.REG_IO))

            else:
                raise ValueError(op)
                
        self.port.execute(pending)

        for op, idx in ridx.items():
            rr = pending[idx]
            in_reg = rr.value
            r = {}
            for io_name in op.ios:
                io = self._ios[io_name]
                r[io_name] = (in_reg >> io.no) & 1
            op.values = r

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1500, idProduct = 0xdeba, bcdDevice = 0x0101))
class Adapter(model.Adapter):
    """
    "target_cortex0" target board multi-protocol firmware, rev 1.01, has most serial protocol transactors
    """
    supported_interfaces = ["cs", "jtag", "swd", "spi", "spi-inv", "i2c", "i2c-int", "i2c-ext", "bb"]

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "df-%s" % (serial,))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.handle = device
        self.io = None

    def _open(self):
        from ..component.nsl.bnoc.routed import Router

        if self.io:
            return

        cfg = self.handle.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.handle.set_configuration(1)
            cfg = self.handle.get_active_configuration()
        for intf in cfg:
            self.logger.debug("Has interface %d, %02x:%02x:%02x",
                  intf.index,
                  intf.bInterfaceClass,
                  intf.bInterfaceSubClass,
                  intf.bInterfaceProtocol)
            if intf.bInterfaceClass == 0xff and \
               intf.bInterfaceSubClass == 0xff and \
               intf.bInterfaceProtocol == 0xff:
                self.intf = intf
                break
        usb.util.claim_interface(self.handle, self.intf)

        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)

        self.logger.debug("Using interface %d, EP_IN: %02x, EP_OUT: %02x",
                          self.intf.index,
                          self.ep_in.bEndpointAddress,
                          self.ep_out.bEndpointAddress)

        self.io = model.BulkDatagramInterface(self, self.handle, "io", self.ep_out, self.ep_in)
        self.child_add(self.io)
        
        r = Router(self.io)
        self.child_add(r)

        self.regs = Registers(r.route(0xf, 0x0).framed_endpoint())
        self.child_add(self.regs)
        self.base_freq = self.regs.base_freq()

        self.swd = SwdInterface(r.route(0xf, 0x1).framed_endpoint(), self.base_freq, self.regs)
        self.jtag = JtagInterface(r.route(0xf, 0x2).framed_endpoint(), self.base_freq, self.regs)
        self.spi = SpiInterface(r.route(0xf, 0x3).framed_endpoint(), self.base_freq, self.regs)
        self.i2c = I2cInterface(r.route(0xf, 0x4).framed_endpoint(), self.base_freq, self.regs)
        self.none = NoneInterface(self.regs)

        self.child_add(self.jtag)
        self.child_add(self.spi)
        self.child_add(self.swd)
        self.child_add(self.i2c)

    def open(self, interface_name):
        self._open()

        if interface_name.lower() == "cs":
            return self.regs

        elif interface_name.lower() == "jtag":
            self.regs.mode_set(Mode.JTAG)
            return self.jtag

        elif interface_name.lower() == "jtag-ext":
            self.regs.mode_set(Mode.JTAG_EXT)
            return self.jtag

        elif interface_name.lower() == "spi":
            self.regs.mode_set(Mode.SPI)
            return self.spi

        elif interface_name.lower() == "spi-inv":
            self.regs.mode_set(Mode.SPI_INV)
            return self.spi

        elif interface_name.lower() == "swd":
            self.regs.mode_set(Mode.SWD)
            return self.swd

        elif interface_name.lower() == "swd-ext":
            self.regs.mode_set(Mode.SWD_EXT)
            return self.swd

        elif interface_name.lower() == "i2c":
            self.regs.mode_set(Mode.I2C_TGT)
            return self.i2c

        elif interface_name.lower() == "i2c-ext":
            self.regs.mode_set(Mode.I2C_EXT)
            return self.i2c

        elif interface_name.lower() == "i2c-int":
            self.regs.mode_set(Mode.I2C_INT)
            return self.i2c

        elif interface_name.lower() == "none":
            self.regs.mode_set(Mode.NONE)
            return self.none

        elif interface_name.lower() == "spi-slave":
            self.regs.mode_set(Mode.SPI_SLAVE)
            return self.none

        elif interface_name.lower() == "spi-slave-inv":
            self.regs.mode_set(Mode.SPI_SLAVE_INV)
            return self.none

        elif interface_name.lower() == "bb":
            self.regs.mode_set(Mode.NONE)
            return BitbangInterface(self)
