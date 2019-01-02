from .. import model
import usb.core
import usb.util
import binascii
import time
import os

__all__ = []

class Adapter(model.Adapter):
    VID_PIDS = []

    @classmethod
    def from_device(cls, d, pre):
        return cls(d, "%s-%d" % (pre, d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device

    def ctrl_out(self, op, value, index, data = b''):
        #self.logger.debug("CTRL OUT %02x v %04x i %04x %s",
        #                  op, value, index,
        #                  binascii.b2a_hex(data))

        self.device.ctrl_transfer(0x40, bRequest = op,
                                  wValue = value, wIndex = index,
                                  data_or_wLength = data)

    def ctrl_in(self, op, value, index, length = 0):
        #self.logger.debug("CTRL IN %02x v %04x i %04x s %d",
        #                  op, value, index, length)

        data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                         wValue = value,
                                         wIndex = index,
                                         data_or_wLength = length)
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def bulk_out(self, ep, data, timeout = None):
        self.logger.debug("BULK OUT %02x %d", ep, len(data))
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        self.logger.debug("BULK IN %02x %d", ep, size)
        data = self.device.read(ep, size, int((timeout or 1.) * 1000))
        #self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    CTRL_MAX_PACKET_SIZE = 4096
    REQ_WRITE = (usb.core.util.ENDPOINT_OUT | usb.core.util.CTRL_TYPE_VENDOR |
                 usb.core.util.CTRL_RECIPIENT_DEVICE)
    REQ_READ = (usb.core.util.ENDPOINT_IN | usb.core.util.CTRL_TYPE_VENDOR |
                usb.core.util.CTRL_RECIPIENT_DEVICE)
    CMD_RW_INTERNAL = 0xA0
    CMD_RW_EEPROM = 0xA2

    def reset(self, enable_cpu):
        cpu_address = 0xE600
        data = bytes([int(bool(enable_cpu))])
        self.mem_write(cpu_address, data)

    def mem_write(self, addr, data):
        self.device.ctrl_transfer(self.REQ_WRITE, self.CMD_RW_INTERNAL,
                                  addr & 0xffff, addr >> 16, data)

    def firmware_load(self, program):
        self.device.set_configuration(0)
        self.reset(True)

        for segment in program:
            for off in range(0, len(segment), self.CTRL_MAX_PACKET_SIZE):
                chunk = segment.data[off : off + self.CTRL_MAX_PACKET_SIZE]
                addr = segment.address + off

                #self.logger.debug("Loading %4d bytes at 0x%08x", len(chunk), addr)

                self.mem_write(addr, chunk)

        self.reset(False)

@model.Enumerator.register
class Enumerator(model.Enumerator):
    adapter_class = Adapter
    prefix = "fx2"

    def __init__(self):
        model.Enumerator.__init__(self, self.prefix)

    def start(self):
        for vid, pid in self.adapter_class.VID_PIDS:
            for dev in usb.core.find(idVendor = vid, idProduct = pid, find_all = True):
                self.child_add(self.adapter_class.from_device(dev, self.prefix))

        model.Enumerator.start(self)
