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

    @classmethod
    def phys_path(cls, bus, address):
        return os.path.realpath(os.path.join(cls.sys_path(bus, address), "port"))

    @classmethod
    def sys_path(cls, bus, address):
        devices = "/sys/bus/usb/devices"
        for d in os.listdir(devices):
            p = os.path.join(devices, d)
            if not os.path.isfile(p + "/devnum"):
                continue
            with open(p + "/devnum", "r") as fd:
                if int(fd.read().strip()) != address:
                    continue
            with open(p + "/busnum", "r") as fd:
                if int(fd.read().strip()) != bus:
                    continue
            return p
        raise KeyError("Device not found")

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device
        self.original_phys_path = self.phys_path(self.device.bus, self.device.address)

    def set_configuration(self, config):
        try:
            cfg = self.device.get_active_configuration()
        except usb.core.USBError:
            cfg = None
        if cfg is None or cfg.bConfigurationValue != config:
            self.device.set_configuration(config)

    def reset(self):
        self.logger.info("Resetting device")
        if False:
            import fcntl
            USBDEVFS_RESET = ord('U') << (4*2) | 20
            path = "/dev/bus/usb/%03d/%03d" % (self.device.bus, self.device.address)
            with open(path, "rb+") as fd:
                fcntl.ioctl(fd, USBDEVFS_RESET, 0)
        else:
            self.device.reset()
        time.sleep(.3)
        self.reopen()

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

    def bulk_out(self, ep, data, timeout = None):
        self.logger.debug("BULK OUT %02x %d", ep, len(data))
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        self.logger.debug("BULK IN %02x %d", ep, size)
        data = self.device.read(ep, size, int((timeout or 1.) * 1000))
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    CTRL_MAX_PACKET_SIZE = 4096
    REQ_WRITE = (usb.core.util.ENDPOINT_OUT | usb.core.util.CTRL_TYPE_VENDOR |
                 usb.core.util.CTRL_RECIPIENT_DEVICE)
    REQ_READ = (usb.core.util.ENDPOINT_IN | usb.core.util.CTRL_TYPE_VENDOR |
                usb.core.util.CTRL_RECIPIENT_DEVICE)
    CMD_RW_INTERNAL = 0xA0
    CMD_RW_EEPROM = 0xA2

    def mem_write(self, addr, data):
        self.ctrl_out(self.CMD_RW_INTERNAL, addr & 0xffff, addr >> 16, data)

    def mem_read(self, addr, size):
        if addr & 1:
            return self.ctrl_in(self.CMD_RW_INTERNAL, (addr & ~1) & 0xffff, addr >> 16, size+1)[1:]
        return self.ctrl_in(self.CMD_RW_INTERNAL, addr & 0xffff, addr >> 16, size)

    def reopen(self):
        self.logger.info("Reopening %s", self.original_phys_path)
        del self.device

        for retry in range(3):
            devices = usb.core.find(find_all = True)
            for d in devices:
                if self.original_phys_path == self.phys_path(d.bus, d.address):
                    self.device = d
                    self.logger.info("Got %d/%d" % (d.bus, d.address))
                    return

            time.sleep(0.2)
        raise RuntimeError("Unable to reopen device")

    def firmware_load(self, program):
        self.logger.debug("Loading %s", program)

        for segment in program:
            off = 0
            while off < len(segment):
                addr = segment.address + off

                s = self.CTRL_MAX_PACKET_SIZE

                chunk = segment.data[off : off + s]

                self.logger.debug("Loading 0x%x/0x%x bytes at 0x%08x", len(chunk), len(segment), addr)

                self.mem_write(addr, chunk)
                readback = self.mem_read(addr, len(chunk))

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

@model.Enumerator.register
class Enumerator(model.Enumerator):
    adapter_class = Adapter
    prefix = "fx"

    def __init__(self):
        model.Enumerator.__init__(self, self.prefix)

    def start(self):
        for vid, pid in self.adapter_class.VID_PIDS:
            for dev in usb.core.find(idVendor = vid, idProduct = pid, find_all = True):
                self.child_add(self.adapter_class.from_device(dev, self.prefix))

        model.Enumerator.start(self)
