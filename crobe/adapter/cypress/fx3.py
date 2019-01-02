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
        return bytes(data)

    def bulk_out(self, ep, data, timeout = None):
        #self.logger.debug("BULK OUT %02x %s", ep, binascii.b2a_hex(data))
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        #self.logger.debug("BULK IN %02x %d", ep, size)
        data = self.device.read(ep, size, int((timeout or 1.) * 1000))
        #self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def is_in_bootloader(self):
        ret = self.ctrl_in(0xf3, index = 0, value = 0, length = 1)
        self.logger.info("Bootloader mode: %s", ret)
        return ret[0] == 1

    def reenumerate(self):
        try:
            self.ctrl_out(0xf2, index = 0, value = 0)
        except:
            self.logger.error("Reenumeration failed")
        time.sleep(.6)

    CTRL_MAX_PACKET_SIZE = 4096
    CMD_RW_INTERNAL = 0xA0

    def firmware_load(self, program):
        self.logger.debug("Loading %s", program)

        for segment in program:
            off = 0
            while off < len(segment):
                addr = segment.address + off

                s = self.CTRL_MAX_PACKET_SIZE

                chunk = segment.data[off : off + s]

                self.logger.debug("Loading 0x%x/0x%x bytes at 0x%08x", len(chunk), len(segment), addr)

                self.ctrl_out(self.CMD_RW_INTERNAL, addr & 0xffff, addr >> 16, chunk)
                readback = self.ctrl_in(self.CMD_RW_INTERNAL, addr & 0xffff, addr >> 16, len(chunk))

                if readback == chunk:
                    off += len(chunk)
                    continue

                for i in range(0, len(chunk), 16):
                    a = chunk[i : i + 16]
                    b = readback[i : i + 16]
                    if a == b:
                        continue
                    self.logger.debug("%08x: w %s", addr + i, binascii.b2a_hex(a))
                    self.logger.debug("%08x: r %s", addr + i, binascii.b2a_hex(b))

                assert readback == chunk

        entry = program.info["entry"]

        self.logger.debug("Setting entry point: 0x%08x" % entry)

        self.ctrl_out(self.CMD_RW_INTERNAL, entry & 0xffff, entry >> 16)

        time.sleep(.6)

    def reopen(self):
        bus = self.device.bus
        address = self.device.address

        self.logger.info("Reopening %d/%d" % (bus, address))

        for retry in range(3):
            devices = usb.core.find(find_all = True)
            for d in devices:
                valid = False

                if d.address == address:
                    valid = True
                elif (d.idVendor, d.idProduct) in self.VID_PIDS:
                    valid = True

                if valid:
                    self.device = d
                    self.logger.info("Got %d/%d" % (bus, address))
                    return

            time.sleep(0.2)
        raise RuntimeError("Unable to reopen device")

@model.Enumerator.register
class Enumerator(model.Enumerator):
    adapter_class = Adapter
    prefix = "fx3"

    def __init__(self):
        model.Enumerator.__init__(self, self.prefix)

    def start(self):
        for vid, pid in self.adapter_class.VID_PIDS:
            for dev in usb.core.find(idVendor = vid, idProduct = pid, find_all = True):
                self.child_add(self.adapter_class.from_device(dev, self.prefix))

        model.Enumerator.start(self)
