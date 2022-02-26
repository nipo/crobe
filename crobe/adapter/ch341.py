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

        
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x1a86, idProduct = 0x5512))
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
    VENDOR_BUFFER_CLEAR = 0xb2

    supported_interfaces = ["i2c", "spi"]

    EP_IN  = 0x82
    EP_OUT = 0x02

    def ctrl_out(self, op, value, index, data = b''):
        self.logger.protocol("CTRL OUT %02x v %04x i %04x %s",
                          op, value, index,
                          binascii.b2a_hex(data))

        self.device.ctrl_transfer(0x40, bRequest = op,
                                  wValue = value, wIndex = index,
                                  data_or_wLength = data)

    def ctrl_in(self, op, value, index, length = 0):
        self.logger.protocol("CTRL IN %02x v %04x i %04x s %d",
                          op, value, index, length)

        data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                         wValue = value,
                                         wIndex = index,
                                         data_or_wLength = length)
        self.logger.protocol("-> %s", binascii.b2a_hex(data))
        return data

    def version_get(self):
        return int.from_bytes(self.ctrl_in(self.VENDOR_VERSION_GET, 0, 0, 2), "little")

    def buffer_clear(self):
        self.ctrl_out(self.VENDOR_BUFFER_CLEAR, 0, 0, b'')

    def bulk_out(self, data, timeout = None):
        self.logger.protocol("BULK OUT %s", binascii.b2a_hex(data))
        self.device.write(self.EP_OUT, data, int((timeout or 1.) * 1000))

    def bulk_in(self, size, timeout = None):
        self.logger.protocol("BULK IN %d", size)
        data = self.device.read(self.EP_IN, size, int((timeout or 1.) * 1000))
        self.logger.protocol("-> %s", binascii.b2a_hex(data))
        return data

    def do_io(self, blob, read_size = 0):
        self.bulk_out(blob)
        if read_size:
            return self.bulk_in(read_size)
        return b''

    @classmethod
    def from_device(cls, d):
        return cls(d, "ch341-%d" % (d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device
        self.version = self.version_get()

    def open(self, interface_name):
        if interface_name.lower() == "i2c":
            return I2cInterface(self)

        elif interface_name.lower() == "spi":
            return SpiInterface(self)

class SpiInterface(spi.Interface):
    def __init__(self, port):
        spi.Interface.__init__(self, port)

        self.child_add(spi.Target(self, "cs0", 0))
        self.child_add(spi.Target(self, "cs1", 1))
        self.child_add(spi.Target(self, "cs2", 2))
        self.child_add(spi.Target(self, "cs3", 3))

        self.__fast = False
        self.__fast_dirty = True

        self.port.buffer_clear()

    def freq_update(self, freq):
        # Bitrate logic disabled, it does not work.
        return 1.5e6

        fast = freq > 1e6
        if self.__fast == fast:
            return
        self.__fast = fast
        self.__fast_dirty = True
        return 1e6 if self.__fast else 500e3

    def _do_spi_shift(self, mosi):
        miso = b''
        mosi = endian.bitswap8(mosi)
        for off in range(0, len(mosi), 0x1f):
            chunk = mosi[off:][:0x1f]
            miso += self.port.do_io(bytes([self.port.CMD_SPI_BEGIN]) + chunk, len(chunk))
        return endian.bitswap8(miso)

    def _do_spi_cs(self, no):
        assert no is None or 0 <= no <= 3
        cs_mask = [0x01, 0x02, 0x04, 0x10][no] if no is not None else 0
        out_val_mask = 0x37 # Keep D3 low
        self.port.do_io(bytes([self.port.CMD_GPIO_BEGIN,
                               self.port.CMD_GPIO_OUT(out_val_mask & ~cs_mask),
                               self.port.CMD_GPIO_OE(0x3f),
                               self.port.CMD_GPIO_END]))

    def _do_spi_rate(self, v):
        self.port.do_io(bytes([self.port.CMD_I2C_BEGIN,
                               self.port.CMD_I2C_RATE(v, 0),
                               self.port.CMD_I2C_END]))

    def _execute(self, operation_list):
        pending = []

        if self.__fast_dirty:
            self.__fast_dirty = False
            self._do_spi_rate(self.__fast)

        for op in operation_list:
            if isinstance(op, spi.Shift):
                if isinstance(op.mosi, int):
                    op.miso = self._do_spi_shift(b'\x00' * op.mosi)
                else:
                    op.miso = self._do_spi_shift(op.mosi)

            elif isinstance(op, spi.Cs):
                self._do_spi_cs(op.value)

            else:
                raise base.ProtocolError("Unknown SPI operation %s" % type(op))

class I2cInterface(i2c.Interface):
    def __init__(self, port):
        i2c.Interface.__init__(self, port)

        self.logger.debug("Version: 0x%04x", self.port.version)
        self.__freq_index = 0
        self.__freq_dirty = True

        # 100k+ has glitches on SCL
        self.freq_cap("crappy hardware", 20e3)

        self.port.buffer_clear()

    def freq_update(self, freq):
        fi = 0
        for i, f in enumerate(self.port.RATE):
            if freq >= f:
                fi = i
        if self.__freq_index != fi:
            self.__freq_index = fi
            self.__freq_dirty = True

        return self.port.RATE[self.__freq_index]

    def i2c_reset(self):
        self.__i2c_req = bytes([self.port.CMD_I2C_BEGIN])
        self.__i2c_rsp_size = 0
        self.__i2c_rsp = b''

    def i2c_flush(self, force = True, req = 0, rsp = 0):
        mps = 0x1f

        if len(self.__i2c_req) > 1 and (force or len(self.__i2c_req) + req > mps or self.__i2c_rsp_size + rsp > mps):
            self.__i2c_req += b"\x00"
            self.__i2c_rsp += self.port.do_io(self.__i2c_req, self.__i2c_rsp_size)
            self.__i2c_req = bytes([self.port.CMD_I2C_BEGIN])
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

            self.logger.trace("op: %s", op)

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
                    raise i2c.AddressNack(op.addr)
            if isinstance(op, i2c.Read):
                op.data = bytes(rsp[op.__rdata_off:op.__rdata_off+op.size])

            elif isinstance(op, i2c.Write):
                for off in op.__ack_off:
                    if rsp[off] != 0x6f:
                        raise i2c.DataNack()
