from .. import model
import usb.core
import usb.util
import binascii
import time
import os

__all__ = []

class Adapter(model.Adapter):
    @classmethod
    def from_device(cls, d, pre = None):
        if pre is None:
            pre = cls.__name__.lower()
        return cls(d, "%s-%d" % (pre, d.address))

    @classmethod
    def persistent_id(cls, dev):
        try:
            return os.path.realpath(os.path.join(cls.sys_path(dev.bus, dev.address), "port"))
        except:
            return "d:%04x:%04x" % (dev.idVendor, dev.idProduct)

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
        self.original_persistent_id = self.persistent_id(self.device)

    def set_configuration(self, config):
        try:
            cfg = self.device.get_active_configuration()
        except usb.core.USBError:
            cfg = None
        if cfg is None or cfg.bConfigurationValue != config:
            self.device.set_configuration(config)

    def reset(self):
        self.logger.trace("Resetting device")
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

    def bulk_out(self, ep, data, timeout = None):
        self.logger.protocol("BULK OUT %02x %d", ep, len(data))
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        self.logger.protocol("BULK IN %02x %d", ep, size)
        data = self.device.read(ep, size, int((timeout or 1.) * 1000))
        self.logger.protocol("-> %s", binascii.b2a_hex(data))
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
        self.logger.trace("Reopening %s", self.original_persistent_id)
        del self.device

        for retry in range(3):
            devices = usb.core.find(find_all = True)
            for d in devices:
                if self.original_persistent_id is not None \
                   and self.original_persistent_id == self.persistent_id(d):
                    self.device = d
                    self.logger.debug("Got %d/%d" % (d.bus, d.address))
                    return

            time.sleep(0.2)
        raise RuntimeError("Unable to reopen device")

    def firmware_load(self, program):
        self.logger.trace("Loading %s", program)

        for segment in program:
            off = 0
            while off < len(segment):
                addr = segment.address + off

                s = self.CTRL_MAX_PACKET_SIZE

                chunk = segment.data[off : off + s]

                self.logger.debug("Loading 0x%x/0x%x bytes at 0x%08x", len(chunk), len(segment), addr)
                
                self.mem_write(addr, chunk)
                off += len(chunk)
                continue

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
