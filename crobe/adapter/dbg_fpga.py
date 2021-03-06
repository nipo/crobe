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
            return SpiInterface(self)

class SpiInterface(spi.Interface):
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
