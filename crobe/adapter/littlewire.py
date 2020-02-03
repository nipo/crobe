from . import model
from ..protocol import i2c, spi
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

__all__ = []

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1781, idProduct = 0x0c9f))
class Adapter(model.Adapter):
    supported_interfaces = ["i2c"]
    def ctrl(self, op, value, index, data_or_size = b''):
        if isinstance(data_or_size, int):
            self.logger.debug("CTRL IN %02x v %04x i %04x s %d",
                              op, value, index, data_or_size)

            data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                             wValue = value,
                                             wIndex = index,
                                             data_or_wLength = data_or_size)
            self.logger.debug("-> %s", binascii.b2a_hex(data))
            return data
        else:
            self.logger.debug("CTRL OUT %02x v %04x i %04x %s",
                              op, value, index,
                              binascii.b2a_hex(data))

            self.device.ctrl_transfer(0x40, bRequest = op,
                                      wValue = value, wIndex = index,
                                      data_or_wLength = data)

    def fw_version_get(self):
        blob = self.ctrl(34, 0, 0, 8)
        v = blob[0]
        return "%d.%d" % (v >> 4, v & 0xf)

    @classmethod
    def from_device(cls, d):
        return cls(d, "lw-%d" % (d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device
        self.fw_version = self.fw_version_get()

    def open(self, interface_name):
        if interface_name.lower() == "i2c":
            return I2cInterface(self)

    def i2c_start(self, addr_byte):
        self.ctrl(45, value = addr_byte, index = 0, data_or_size = 8)
        r = self.ctrl(40, value = 0, index = 0, data_or_size = 8)
        return bool(r[0])

    def i2c_write(self, blob, stop_at_end):
        assert len(blob) <= 4 and blob
        b = blob.ljust(4, b'\x00')
        r = self.ctrl(0xe0 | len(blob) | (8 if stop_at_end else 0),
                      value = b[0] | (b[1] << 8),
                      index = b[2] | (b[3] << 8),
                      data_or_size = 8)
        return r

    def i2c_read(self, size, stop_at_end):
        stop = int(bool(stop_at_end))
        self.ctrl(46, value = (size << 8) | stop, index = stop, data_or_size = 8)
        data = self.ctrl(40, value = 0, index = 0, data_or_size = 8)
        return data[:size]

    def i2c_delay_set(self, duration):
        self.ctrl(49, value = duration, index = 0, data_or_size = 8)
        
class I2cInterface(i2c.Interface):
    def __init__(self, port):
        i2c.Interface.__init__(self, port)
        self.logger.info("Version: %s", self.port.fw_version)
        self.__delay = 0
        self.port.i2c_delay_set(0)

    I2C_BIT_PERIOD = 2.5e-6
    I2C_DELAY_PERIOD = 4.4e-6
        
    @property
    def freq(self):
        return 1 / (self.I2C_BIT_PERIOD + self.I2C_DELAY_PERIOD * self.__delay)

    @freq.setter
    def freq(self, freq):
        delay = int(math.ceil((1 / float(freq) - self.I2C_BIT_PERIOD) / self.I2C_DELAY_PERIOD))
        self.__delay = delay
        self.port.i2c_delay_set(delay)

    def _execute(self, operation_list):
        ops = list(operation_list)
        prev = None

        for idx, op in enumerate(ops):
            as_prev = bool(prev) and isinstance(prev, i2c.Read) == isinstance(op, i2c.Read)
            last = idx == len(ops) - 1

            self.logger.info("op: %s", op)

            if isinstance(op, i2c.Read):
                is_last = idx == len(ops)-1 or not isinstance(ops[idx], i2c.Read)
                if not as_prev:
                    ack_bit = self.port.i2c_start((op.addr << 1) | 1)
                    if ack_bit:
                        raise i2c.AddressNack(op.addr)
                r = b''
                for off in range(0, op.size, 4):
                    size = min(op.size - off, 4)
                    end = off + size >= op.size
                    r += self.port.i2c_read(size, end and last)
                op.data = r

            elif isinstance(op, i2c.Write):
                if not as_prev:
                    ack_bit = self.port.i2c_start(op.addr << 1)
                    if ack_bit:
                        raise i2c.AddressNack(op.addr)

                for off in range(0, len(op.data), 4):
                    size = min(len(op.data) - off, 4)
                    end = off + size >= len(op.data)
                    self.port.i2c_write(op.data[off : off + size], end and last)

            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))
