from . import model
from ..protocol import i2c
from .. import bitstring
from ..util.pretty import metric
from collections import deque
import usb.core
import usb.util
import binascii
import time
import os
import math
import struct
import threading

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

class Adapter(model.Adapter):
    RATE = [20e3, 100e3, 400e3, 750e3]

    CMD_I2C_BEGIN  = 0xAA
    CMD_I2C_RATE   = staticmethod(lambda spi_fast, i2c_rate: 0x60 | (int(bool(spi_fast)) << 4) | i2c_rate)
    CMD_I2C_OUT    = staticmethod(lambda length: 0x80 | (length & 0x1f))
    CMD_I2C_IN     = staticmethod(lambda length: 0xc0 | (length & 0x1f))
    CMD_I2C_START  = 0x74
    CMD_I2C_STOP   = 0x75
    CMD_I2C_WAIT_MS = staticmethod(lambda ms: 0x50 | (ms & 0xf))
    CMD_I2C_WAIT_US = staticmethod(lambda us: 0x40 | (us & 0xf))
    CMD_I2C_END    = 0x00

    CMD_GPIO_BEGIN  = 0xAB
    CMD_GPIO_OUT = staticmethod(lambda io: 0x80 | (io & 0x3f))
    CMD_GPIO_OE  = staticmethod(lambda io: 0x40 | (io & 0x3f))
    CMD_GPIO_IN  = 0x00
    CMD_GPIO_END = 0x20

    CMD_SPI_BEGIN  = 0xA8

    VENDOR_VERSION_GET = 0x5F

    supported_interfaces = ["i2c"]

    EP_IN  = 0x82
    EP_OUT = 0x02

    def ctrl_out(self, op, value, index, data = b''):
        self.logger.debug("CTRL OUT %02x v %04x i %04x %s",
                          op, value, index,
                          binascii.b2a_hex(data))

        self.device.ctrl_transfer(0x40, bRequest = op,
                                  wValue = value, wIndex = index,
                                  data_or_wLength = data)

    def ctrl_in(self, op, value, index, length = 0):
        self.logger.debug("CTRL IN %02x v %04x i %04x s %d",
                          op, value, index, length)

        data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                         wValue = value,
                                         wIndex = index,
                                         data_or_wLength = length)
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def version_get(self):
        return int.from_bytes(self.ctrl_in(self.VENDOR_VERSION_GET, 0, 0, 2), "little")
    
    def bulk_out(self, data, timeout = None):
        self.logger.debug("BULK OUT %s", binascii.b2a_hex(data))
        self.device.write(self.EP_OUT, data, int((timeout or 1.) * 1000))

    def bulk_in(self, size, timeout = None):
        self.logger.debug("BULK IN %d", size)
        data = self.device.read(self.EP_IN, size, int((timeout or 1.) * 1000))
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    @classmethod
    def from_device(cls, d, pre):
        return cls(d, "%s-%d" % (pre, d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device
        self.version = self.version_get()

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        if interface_name.lower() == "i2c":
            return I2cInterface(self)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class I2cInterface(i2c.Interface):
    def __init__(self, port):
        i2c.Interface.__init__(self, port)

        self.logger.info("Version: 0x%04x", self.port.version)
        self.__freq_index = 0
        self.__freq_dirty = True

        # 100k+ has glitches on SCL
        self.freq_cap("crappy hardware", 20e3)
        
    @property
    def freq(self):
        return self.port.RATE[self.__freq_index]

    @freq.setter
    def freq(self, freq):
        fi = 0
        for i, f in enumerate(self.port.RATE):
            if freq >= f:
                fi = i
        if self.__freq_index != fi:
            self.__freq_index = fi
            self.__freq_dirty = True

    def i2c_reset(self):
        self.__i2c_req = bytes([self.port.CMD_I2C_BEGIN])
        self.__i2c_rsp_size = 0
        self.__i2c_rsp = b''

    def i2c_flush(self, force = True, req = 0, rsp = 0):
        mps = 0x1f

        if len(self.__i2c_req) > 1 and (force or len(self.__i2c_req) + req > mps or self.__i2c_rsp_size + rsp > mps):
            self.__i2c_req += b"\x00"
            self.port.bulk_out(self.__i2c_req)
            self.__i2c_req = bytes([self.port.CMD_I2C_BEGIN])

            if self.__i2c_rsp_size:
                self.__i2c_rsp += self.port.bulk_in(self.__i2c_rsp_size)
                self.__i2c_rsp_size = 0

        return self.__i2c_rsp

    def i2c_append(self, req = b'', rsp = 0):
        self.i2c_flush(force = False, req = len(req), rsp = rsp)

        self.__i2c_req += req
        off = self.__i2c_rsp_size
        self.__i2c_rsp_size += rsp
        return len(self.__i2c_rsp) + off

    def i2c_rate(self, v):
        self.i2c_append(bytes([self.port.CMD_I2C_RATE(0, v)]))

    def i2c_wait_us(self, v):
        self.i2c_append(bytes([self.port.CMD_I2C_WAIT_US(v)]))

    def i2c_wait_ms(self, v):
        self.i2c_append(bytes([self.port.CMD_I2C_WAIT_MS(v)]))

    def i2c_start(self):
        return self.i2c_append(bytes([self.port.CMD_I2C_START]))

    def i2c_stop(self):
        return self.i2c_append(bytes([self.port.CMD_I2C_STOP]))

    def i2c_out(self, b):
        return self.i2c_append(bytes([self.port.CMD_I2C_OUT(0), b]), 1)

    def i2c_in(self, length, ack_last):
        r = []
        if ack_last:
            for off in range(0, length, 15):
                l = min(length - off, 15)
                r.append(self.i2c_append(bytes([self.port.CMD_I2C_IN(l)]), l))
        else:
            for off in range(0, length-1, 15):
                l = min(length-1 - off, 15)
                r.append(self.i2c_append(bytes([self.port.CMD_I2C_IN(l)]), l))
            r.append(self.i2c_append(bytes([self.port.CMD_I2C_IN(0)]), 1))
        return r[0]

    def _execute(self, operation_list):
        ops = list(operation_list)
        prev = None

        self.i2c_reset()

        if self.__freq_dirty:
            self.i2c_rate(self.__freq_index)
            self.__freq_dirty = False
        
        for idx, op in enumerate(ops):
            as_prev = bool(prev) and isinstance(prev, i2c.Read) == isinstance(op, i2c.Read)

            self.logger.info("op: %s", op)

            if isinstance(op, i2c.Read):
                is_last = idx == len(ops)-1 or not isinstance(ops[idx], i2c.Read)
                if not as_prev:
                    self.i2c_wait_us(10)
                    self.i2c_wait_us(10)
                    self.i2c_start()
                    op.__saddr_ack = self.i2c_out((op.addr << 1) | 1)
                    self.i2c_wait_us(10)
                    self.i2c_wait_us(10)
                else:
                    op.__saddr_ack = None
                op.__rdata_off = self.i2c_in(op.size, not is_last)

            elif isinstance(op, i2c.Write):
                if not as_prev:
                    self.i2c_wait_us(10)
                    self.i2c_wait_us(10)
                    self.i2c_start()
                    op.__saddr_ack = self.i2c_out(op.addr << 1)
                    self.i2c_wait_us(10)
                    self.i2c_wait_us(10)
                else:
                    op.__saddr_ack = None
                op.__ack_off = []
                for b in op.data:
                    op.__ack_off.append(self.i2c_out(b))
            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))
        self.i2c_stop()
        rsp = self.i2c_flush(True)

        for op in ops:
            if op.__saddr_ack is not None:
                if rsp[op.__saddr_ack] != 0x6f:
                    raise i2c.AddressNack()
            if isinstance(op, i2c.Read):
                op.data = bytes(rsp[op.__rdata_off:op.__rdata_off+op.size])

            elif isinstance(op, i2c.Write):
                for off in op.__ack_off:
                    if rsp[off] != 0x6f:
                        raise i2c.DataNack()

@model.Enumerator.register
class Enumerator(model.Enumerator):
    adapter_class = Adapter
    prefix = "CH341A"

    def __init__(self):
        model.Enumerator.__init__(self, self.prefix)

    def start(self):
        for dev in usb.core.find(idVendor = 0x1a86, idProduct = 0x5512, find_all = True):
            self.child_add(self.adapter_class.from_device(dev, self.prefix))
        model.Enumerator.start(self)
