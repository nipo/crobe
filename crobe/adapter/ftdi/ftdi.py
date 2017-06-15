from . import libftdi as ftdi
import ctypes
import struct
import logging

class FtdiError(Exception):
    pass

class Context(object):
    def __init__(self):
        self.context = ftdi.new()
        self.logger = logging.getLogger("ftdi")

    def __del__(self):
        if ftdi:
            ftdi.free(self.context)

    def check(self, ret):
        if ret < 0:
            errorstring = str(ftdi.get_error_string(self.context), 'utf-8')
            raise FtdiError(errorstring, ret)
        return ret

class Enumerator(Context):
    def __init__(self):
        Context.__init__(self)

    def find_all(self, vid, pid):
        ret = []

        self.logger.info("Looking for %04x:%04x...", vid, pid)
        
        devlist = ctypes.POINTER(ftdi.device_list)()
        count = self.check(ftdi.usb_find_all(self.context, ctypes.byref(devlist), vid, pid))

        cur = ctypes.POINTER(ftdi.device_list)(devlist.contents)
        
        while cur:
            d = Device(self, cur.contents.dev)
            self.logger.info("Found %s", d)
            ret.append(d)
            cur = cur.contents.next

        return ret

class Device(object):
    def __init__(self, context, dev):
        vendor = (ctypes.c_char * 32)()
        model = (ctypes.c_char * 32)()
        serial = (ctypes.c_char * 32)()
        
        context.check(ftdi.usb_get_strings(context.context, dev, vendor, 32, model, 32, serial, 32))

        self.vendor = str(vendor.value, "utf-8")
        self.model = str(model.value, "utf-8")
        self.serial = str(serial.value, "utf-8")

        self.connection_id = b"d:%03u/%03u" % (ftdi.libusb_get_bus_number(dev), ftdi.libusb_get_device_address(dev))
        
    def open(self):
        return Handle(self)
        
    def __str__(self):
        return "<FTDI Device %r %r %r>" % (self.vendor, self.model, self.serial)

class Handle(Context):
    def __init__(self, device):
        Context.__init__(self)
        self.device = device

        self.check(ftdi.set_interface(self.context, ftdi.INTERFACE["A"]))
        self.check(ftdi.usb_open_string(self.context, self.device.connection_id))
        self.check(ftdi.read_eeprom(self.context))
        self.check(ftdi.eeprom_decode(self.context, 0))
        self.check(ftdi.set_bitmode(self.context, 0, ftdi.BITMODE["RESET"]))
        self.check(ftdi.usb_purge_buffers(self.context))
        self.check(ftdi.set_latency_timer(self.context, 1))
        print("init: %r" % self.read(5))

    def eeprom_dump(self):
        for name in ftdi.EEPROM_VALUE:
            try:
                print(name, self.eeprom_value_get(name))
            except FtdiError:
                pass

    def jtag(self):
        self.check(ftdi.set_bitmode(self.context, 0xfb, ftdi.BITMODE["MPSSE"]))
        return Jtag(self)
            
    def eeprom_value_get(self, name):
        value = ctypes.c_int()
        id = ftdi.EEPROM_VALUE[name]
        self.check(ftdi.get_eeprom_value(self.context, id, ctypes.byref(value)))
        revmap = dict(
            CHANNEL_A_TYPE = ftdi.CHANNEL_TYPE_NAME,
            CHANNEL_B_TYPE = ftdi.CHANNEL_TYPE_NAME,
            CHANNEL_A_DRIVER = ftdi.DRIVER_NAME,
            CHANNEL_B_DRIVER = ftdi.DRIVER_NAME,
            CHANNEL_C_DRIVER = ftdi.DRIVER_NAME,
            CHANNEL_D_DRIVER = ftdi.DRIVER_NAME,
            CBUS_FUNCTION_0 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_1 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_2 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_3 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_4 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_5 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_6 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_7 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_8 = ftdi.CBUS_NAME,
            CBUS_FUNCTION_9 = ftdi.CBUS_NAME,
            GROUP0_DRIVE = ftdi.DRIVE_NAME,
            GROUP1_DRIVE = ftdi.DRIVE_NAME,
            GROUP2_DRIVE = ftdi.DRIVE_NAME,
            GROUP3_DRIVE = ftdi.DRIVE_NAME,
            CHIP_TYPE = ftdi.CHIP_TYPE_NAME,
            )
        try:
            rev = revmap[name]
            return rev[value.value]
        except:
            return value.value

    def write(self, blob):
        raw = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        self.check(ftdi.write_data(self.context, raw, len(blob)))

    def read(self, size = 4096):
        blob = (ctypes.c_ubyte * size)()
        size = self.check(ftdi.write_data(self.context, blob, size))
        return bytes(blob[:size])

    def direction_set(self, outputs, high = 0):
        cmd = bytes([ftdi.MPSSE_SET_BITS_LOW, (high & 0xf0) | 0x08, (outputs & 0xf0) | 0x0b,
                     ftdi.MPSSE_SET_BITS_HIGH, high >> 8, outputs >> 8,
                     ftdi.MPSSE_CLK_DIV5_DISABLE,
                     ftdi.MPSSE_3_PHASE_DISABLE,
                     ftdi.MPSSE_ADAPTIVE_DISABLE,
                     ftdi.MPSSE_LOOPBACK_DISABLE,
                     ftdi.MPSSE_CLK_DIV, 59, 0])
        self.write(cmd)
        print("response: %r" % self.read())

class Jtag(object):
    def __init__(self, handle):
        self.handle = handle

    def execute(self, cmds):
        pass
    
def main():
    adapters = Enumerator().find_all(0x0403, 0x6014)
#    adapters = Enumerator().find_all(0x10eb, 0x0026)
    jtag = adapters[0].open().jtag()
    jtag.handle.direction_set(0x60eb, 0x00e8)
    
if __name__ == '__main__':
    main()
