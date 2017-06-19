from . import api
from ...bitstring import BitString
from ... import model
from ..protocol import base, jtag
import ctypes
import struct
import logging
import binascii

class FtdiError(base.CommunicationError):
    pass

class Context(object):
    def __init__(self):
        self.context = api.new()

    def __del__(self):
        if api:
            api.free(self.context)

    def check(self, ret):
        if ret < 0:
            errorstring = str(api.get_error_string(self.context), 'utf-8')
            raise FtdiError(errorstring, ret)
        return ret

class Device(object):
    @classmethod
    def list_all(self, vid, pid):
        devlist = ctypes.POINTER(api.device_list)()
        c = Context()

        count = c.check(api.usb_find_all(c.context, ctypes.byref(devlist), vid, pid))
        if not count:
            return []

        ret = []
        cur = ctypes.POINTER(api.device_list)(devlist.contents)
        while cur:
            d = Device.from_dev(c, cur.contents.dev, vid, pid)
            
            ret.append(d)

            cur = cur.contents.next

        api.list_free2(devlist)

        return ret

    @classmethod
    def from_dev(cls, ctx, dev, vid, pid):
        vendor, model, serial = "", "", ""

        try:
            blob = (ctypes.c_char * 32)()
            ctx.check(api.usb_get_strings(ctx.context, dev, blob, 32, None, 0, None, 0))
            vendor = str(blob.value, "utf-8")
        except:
            pass
        
        try:
            blob = (ctypes.c_char * 32)()
            ctx.check(api.usb_get_strings(ctx.context, dev, None, 0, blob, 32, None, 0))
            model = str(blob.value, "utf-8")
        except:
            pass
        
        try:
            blob = (ctypes.c_char * 32)()
            ctx.check(api.usb_get_strings(ctx.context, dev, None, 0, None, 0, blob, 32))
            serial = str(blob.value, "utf-8")
        except:
            pass

        connection_id = b"d:%03u/%03u" % (api.libusb_get_bus_number(dev), api.libusb_get_device_address(dev))

        return cls(vid, pid, vendor, model, serial, connection_id)
    
    def __init__(self, vid, pid, vendor, model, serial, connection_id):
        self.vid = vid
        self.pid = pid
        self.vendor = vendor
        self.model = model
        self.serial = serial
        self.connection_id = connection_id
        self.logger = logging.getLogger(str(self.connection_id, "ascii"))
        
    def __str__(self):
        return "<%s %r %r %r>" % (self.connection_id, self.vendor, self.model, self.serial)
        
    def open(self, interface = "A", mode = "mpsse", **defaults):
        if mode == "mpsse":
            return Mpsse(self, interface, **defaults)

class Handle(Context):
    def __init__(self, device, interface, mode, gpio_oe = 0, gpio_val = 0):
        Context.__init__(self)
        self.device = device

        self.__gpio_oe = gpio_oe
        self.__gpio_val = gpio_val
        self.__speed = 1000000

        self.check(api.set_interface(self.context, api.INTERFACE[interface]))
        self.check(api.usb_open_string(self.context, self.device.connection_id))
        try:
            self.check(api.read_eeprom(self.context))
            self.check(api.eeprom_decode(self.context, 0))
            self.__has_eeprom = True
        except:
            self.__has_eeprom = False
        self.check(api.set_bitmode(self.context, 0, api.BITMODE["RESET"]))
        self.check(api.usb_purge_buffers(self.context))
        self.check(api.set_latency_timer(self.context, 1))
        self.check(api.set_bitmode(self.context, 0xfb, api.BITMODE[mode]))

        self.device.logger.info("init")        
        self.execute(bytes([api.MPSSE_3_PHASE_DISABLE,
                            api.MPSSE_ADAPTIVE_DISABLE,
                            api.MPSSE_LOOPBACK_DISABLE])
                     + self.cmd_gpio_mask_set(0xffff, gpio_oe, gpio_val))

        self.speed = 1000000
        
    @property
    def last_gpio(self):
        return self.__gpio_oe & self.__gpio_val
        
    @property
    def speed(self):
        return self.__speed

    @speed.setter
    def speed(self, speed):
        divisor = 120000000 / speed
        if divisor >= 65535:
            divisor /= 5
            d = min((max((int(divisor) - 1, 0)), 65535))
            self.execute(struct.pack("<BBH",
                                     api.MPSSE_CLK_DIV5_ENABLE,
                                     api.MPSSE_CLK_DIV, d))
            self.__speed = 24000000 // (d + 1)
        else:
            d = min((max((int(divisor) - 1, 0)), 65535))
            self.execute(struct.pack("<BBH",
                                     api.MPSSE_CLK_DIV5_DISABLE,
                                     api.MPSSE_CLK_DIV, int(divisor - 1)))
            self.__speed = 120000000 // (d + 1)
        
        
    def eeprom_dump(self):
        for name in api.EEPROM_VALUE:
            try:
                print(name, self.eeprom_value_get(name))
            except FtdiError:
                pass
            
    def eeprom_value_get(self, name):
        if not self.__has_eeprom:
            raise KeyError("No valid eeprom")

        value = ctypes.c_int()
        id = api.EEPROM_VALUE[name]
        self.check(api.get_eeprom_value(self.context, id, ctypes.byref(value)))
        revmap = dict(
            CHANNEL_A_TYPE = api.CHANNEL_TYPE_NAME,
            CHANNEL_B_TYPE = api.CHANNEL_TYPE_NAME,
            CHANNEL_A_DRIVER = api.DRIVER_NAME,
            CHANNEL_B_DRIVER = api.DRIVER_NAME,
            CHANNEL_C_DRIVER = api.DRIVER_NAME,
            CHANNEL_D_DRIVER = api.DRIVER_NAME,
            CBUS_FUNCTION_0 = api.CBUS_NAME,
            CBUS_FUNCTION_1 = api.CBUS_NAME,
            CBUS_FUNCTION_2 = api.CBUS_NAME,
            CBUS_FUNCTION_3 = api.CBUS_NAME,
            CBUS_FUNCTION_4 = api.CBUS_NAME,
            CBUS_FUNCTION_5 = api.CBUS_NAME,
            CBUS_FUNCTION_6 = api.CBUS_NAME,
            CBUS_FUNCTION_7 = api.CBUS_NAME,
            CBUS_FUNCTION_8 = api.CBUS_NAME,
            CBUS_FUNCTION_9 = api.CBUS_NAME,
            GROUP0_DRIVE = api.DRIVE_NAME,
            GROUP1_DRIVE = api.DRIVE_NAME,
            GROUP2_DRIVE = api.DRIVE_NAME,
            GROUP3_DRIVE = api.DRIVE_NAME,
            CHIP_TYPE = api.CHIP_TYPE_NAME,
            )
        try:
            rev = revmap[name]
            return rev[value.value]
        except:
            return value.value

    def write(self, blob):
        raw = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        self.check(api.write_data(self.context, raw, len(blob)))

    def status(self):
        status = ctypes.c_ushort()
        self.check(api.poll_modem_status(self.context, ctypes.byref(status)))
        return status.value

    def _read(self, size = 4096):
        blob = (ctypes.c_ubyte * size)()
        size = self.check(api.read_data(self.context, blob, size))
        return bytes(blob[:size])

    def read(self, rsize):
        ret = b""
        retries = 1000
        while len(ret) < rsize:
            chunk = self._read(rsize - len(ret))
            if chunk:
                retries += 1000
            ret += chunk
            retries -= 1
            if not retries:
                raise base.CommunicationError("Failed to read all data")
        return ret
    
    def execute(self, blob, rsize = 0):
        self.device.logger.debug("MPSSE commands: %s", binascii.b2a_hex(blob))
        self.write(blob)
        if rsize:
            rsp = self.read(rsize)
            self.device.logger.debug("MPSSE response: %s", binascii.b2a_hex(rsp))
            return rsp
        else:
            self.status()

    def gpio_get(self, pin):
        if pin < 8:
            cmd = bytes([api.MPSSE_GET_BITS_LOW])
        else:
            cmd = bytes([api.MPSSE_GET_BITS_HIGH])
        rsp = self.execute(cmd, 1)
        return bool(rsp[0] & (1 << (pin & 7)))

    def gpio_set(self, pin, value):
        return self.gpio_mask_set(1 << pin, 1 << pin, (1 << pin) if value else 0)

    def gpio_mask_set(self, change_mask, oe, val):
        cmd = self.cmd_gpio_mask_set(change_mask, oe, val)
        self.execute(cmd)
        
    def cmd_gpio_mask_set(self, change_mask, oe, val):
        cmd = bytes()

        self.__gpio_oe = (self.__gpio_oe & ~change_mask) | (change_mask & oe)
        self.__gpio_val = (self.__gpio_val & ~change_mask) | (change_mask & val)

        if change_mask & 0x00ff:
            cmd += bytes([api.MPSSE_SET_BITS_LOW, self.__gpio_val & 0xff, self.__gpio_oe & 0xff])
        if change_mask & 0xff00:
            cmd += bytes([api.MPSSE_SET_BITS_HIGH, (self.__gpio_val >> 8), (self.__gpio_oe >> 8)])

        return cmd

class Mpsse(Handle):
    def __init__(self, device, interface, **defaults):
        Handle.__init__(self, device, interface, "MPSSE", **defaults)

    def cmd_tms_shift(self, tms, next = 0):
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS
        ret = bytes()

        l = len(tms)
        
        for i in range(0, l, 6):
            bits = tms[i : min((i + 7, l))]
            ret += bytes([cmd | api.MPSSE_BITS, len(bits) - 1, int(bits) | (next << 7)])

        return ret

    def cmd_reset(self):
        return self.cmd_tms_shift(BitString(-1, 5))

    def cmd_run(self, count):
        return self.cmd_tms_shift(BitString(0, count))

    def cmd_ir(self):
        return self.cmd_tms_shift(BitString(0b01011, 5))

    def cmd_dr(self):
        return self.cmd_tms_shift(BitString(0b0101, 4))

    def cmd_update(self):
        return self.cmd_tms_shift(BitString(0b011, 3))

    def cmd_shift_io(self, tdi):
        if not len(tdi):
            return b'', []

        counts = []
        tms_cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS | api.MPSSE_BITS
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE
        read = api.MPSSE_READ

        ret = bytes()
        
        bits = len(tdi) - 1
        last = int(tdi[-1])
        data = tdi[:-1].data

        ret += bytes([tms_cmd, 1, (int(tdi[0]) << 7) | 0b01])
        
        if bits:
            if bits >= 8:
                bytestring = data
                if bits % 8:
                    bytestring = bytestring[:-1]
                    
                for i in range(0, len(bytestring), 1024):
                    chunk = bytestring[i : i+1024]
                    ret += struct.pack("<BH", cmd | read, len(chunk) - 1)
                    ret += chunk
                    counts.append((len(chunk), None))
                    
            if bits % 8:
                ret += bytes([cmd | read | api.MPSSE_BITS, (bits % 8) - 1, data[-1]])
                counts.append((1, bits % 8))

        ret += bytes([tms_cmd | read, 0, 0x01 | (last << 7)])
        counts.append((1, 1))

        ret += bytes([tms_cmd, 0, 0])
        
        return ret, counts

    def cmd_shift_out(self, tdi):
        if not len(tdi):
            return b''

        tms_cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS | api.MPSSE_BITS
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE

        ret = bytes()
        
        bits = len(tdi) - 1
        last = int(tdi[-1])
        data = tdi[:-1].data

        ret += bytes([tms_cmd, 1, (int(tdi[0]) << 7) | 0b01])
        
        if bits:
            if bits >= 8:
                bytestring = data
                if bits % 8:
                    bytestring = bytestring[:-1]
                    
                for i in range(0, len(bytestring), 1024):
                    chunk = bytestring[i : i+1024]
                    ret += struct.pack("<BH", cmd, len(chunk) - 1)
                    ret += chunk
                    
            if bits % 8:
                ret += bytes([cmd | api.MPSSE_BITS, (bits % 8) - 1, data[-1]])

        ret += bytes([tms_cmd, 2, 0b01 | (last << 7)])
        
        return ret

    def cmd_out(self, tdi):
        if not len(tdi):
            return b''
        
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE

        ret = bytes()
        bits = len(tdi)
        data = tdi.data
        
        if bits >= 8:
            bytestring = data
            if bits % 8:
                bytestring = bytestring[:-1]

            for i in range(0, len(bytestring), 1024):
                chunk = bytestring[i : i+1024]
                ret += struct.pack("<BH", cmd, len(chunk) - 1)
                ret += chunk

        if bits % 8:
            ret += bytes([cmd | api.MPSSE_BITS, (bits % 8) - 1, data[-1]])
            
        return ret

    def cmd_in(self, bits):
        if not bits:
            return b''

        counts = []

        cmd = api.MPSSE_LSB | api.MPSSE_READ

        ret = bytes()
        
        if bits >= 8:
            ret += struct.pack("<BH", cmd, (bits // 8) - 1)
            counts.append((bits // 8, None))

        if bits % 8:
            ret += bytes([cmd | api.MPSSE_BITS, (bits % 8) - 1])
            counts.append((1, bits % 8))
        
        return ret, counts

    def cmd_idle(self, cycles, value):
        assert cycles

        return self.cmd_out(BitString(-value, cycles))
        
def main():
    import time
    adapters = Device.list_all(0x10eb, 0x26)
    mpsse = adapters[0].open()
#    mpsse.gpio_mask_set(0xffff, 0x60eb, 0x00e8)
#
#    mpsse.speed = 1000
#    
#    cmd = bytes([api.MPSSE_LOOPBACK_ENABLE])
#    print("cmd", binascii.b2a_hex(cmd))
#    print("rsp", binascii.b2a_hex(mpsse.execute(cmd)))
#
#    for i in range(25):
#        print()
#        print(i)
#        cmd = mpsse.cmd_shift(BitString(0x01010101, i))
#        rlen = ((i-1) // 8 + 1) if i else 0
#        print("cmd", binascii.b2a_hex(cmd), rlen)
#        print("rsp", binascii.b2a_hex(mpsse.execute(cmd, rlen)))
    while True:
        mpsse.gpio_mask_set(0xffff, 0xffff, 0)
        time.sleep(1)
        mpsse.gpio_mask_set(0xffff, 0xffff, 0xffff)
        time.sleep(1)

if __name__ == '__main__':
    main()
