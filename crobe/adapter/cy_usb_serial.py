from . import model
from ..protocol import jtag, base
from .. import bitstring
from ..util.pretty import metric
from . import openjtag
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

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x4b4, idProduct = 0x7))
class Adapter(model.Adapter):
    supported_interfaces = ["jtag"]
    def ctrl(self, op, value, index, data_or_size = b''):
        if isinstance(data_or_size, int):
            self.logger.debug("CTRL IN %02x v %04x i %04x s %d",
                              op, value, index, data_or_size)

            data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                             wValue = value,
                                             wIndex = index,
                                             data_or_wLength = data_or_size)
            self.logger.debug("-> %s", data.hex())
            return data
        else:
            self.logger.debug("CTRL OUT %02x v %04x i %04x %s",
                              op, value, index,
                              data_or_size.hex())

            self.device.ctrl_transfer(0x40, bRequest = op,
                                      wValue = value, wIndex = index,
                                      data_or_wLength = data_or_size)

    def bulk_out(self, ep, data, timeout = None):
        self.logger.debug("Bulk %02x OUT << %s", ep, data.hex())
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        self.logger.debug("Bulk %02x IN %d", ep, size)
        data = self.device.read(ep, size, int((timeout or 1.) * 1000))
        data = bytes(data)
        self.logger.debug(">> %s", data.hex())
        return data

    @classmethod
    def from_device(cls, d):
        return cls(d, "lw-%d" % (d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device

    def open(self, interface_name):
        if self.device.is_kernel_driver_active(0):
            self.device.detach_kernel_driver(0)
        if self.device.is_kernel_driver_active(1):
            self.device.detach_kernel_driver(1)

        if interface_name.lower() == "jtag":
            return JtagInterface(self)

class JtagInterface(jtag.Interface):
    JTAG_ENABLE = 0xd0
    JTAG_DISABLE = 0xd1
    JTAG_READ = 0xd2
    JTAG_WRITE = 0xd3

    ep_out = 4
    ep_in = 0x85
    max_size = 256
    
    def __init__(self, adapter):
        self.adapter = adapter
        self.openjtag = openjtag.OpenJtag(self, 48e6)
        super().__init__(adapter)
        self.jtag_enable()

    def freq_update(self, freq):
        return 450e3
        
    def jtag_enable(self):
        return self.adapter.ctrl(op = self.JTAG_ENABLE,
                                 value = 0,
                                 index = 0)

    def jtag_disable(self):
        return self.adapter.ctrl(op = self.JTAG_DISABLE,
                                 value = 0,
                                 index = 0)

    def write(self, data, timeout = 1):
        if not data:
            return
        self.adapter.ctrl(op = self.JTAG_WRITE, value = len(data), index = 0)
        self.adapter.bulk_out(self.ep_out, data, int(timeout * 1000))

    def read(self, size, timeout = 1):
        if not size:
            return b''
        self.adapter.ctrl(op = self.JTAG_READ, value = size, index = 0)
        return self.adapter.bulk_in(self.ep_in, size, int(timeout * 1000))

    def execute(self, operations):
        self.openjtag.jtag_execute(operations)
