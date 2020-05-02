from . import api
from ...bitstring import BitString
from ... import model
from ...protocol import base, jtag
from collections import deque
import ctypes
import struct
import logging
import binascii
import threading
import queue
import math

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
        except Exception:
            pass
        
        try:
            blob = (ctypes.c_char * 32)()
            ctx.check(api.usb_get_strings(ctx.context, dev, None, 0, blob, 32, None, 0))
            model = str(blob.value, "utf-8")
        except Exception:
            pass
        
        try:
            blob = (ctypes.c_char * 32)()
            ctx.check(api.usb_get_strings(ctx.context, dev, None, 0, None, 0, blob, 32))
            serial = str(blob.value, "utf-8")
        except Exception:
            pass

        connection_id = b"d:%03u/%03u" % (api.libusb_get_bus_number(dev), api.libusb_get_device_address(dev))

        return cls(vid, pid, vendor, model, serial, connection_id)

    def reset(self):
        try:
            Handle(self.connection_id, "A", "RESET").close()
        except Exception:
            pass
        try:
            Handle(self.connection_id, "B", "RESET").close()
        except Exception:
            pass
    
    def __init__(self, vid, pid, vendor, model, serial, connection_id):
        self.vid = vid
        self.pid = pid
        self.vendor = vendor
        self.model = model
        self.serial = serial
        self.connection_id = connection_id
        
    def __str__(self):
        return "<%s %r %r %r>" % (self.connection_id, self.vendor, self.model, self.serial)
        
    def open(self, interface = "A", mode = "mpsse", **defaults):
        if mode == "mpsse":
            return Mpsse(self, interface, **defaults)
        elif mode == "ft245_sync_fifo":
            return Handle(self.connection_id, interface, "SYNCFF")
            return Ft245SyncFifo(self, interface, **defaults)
        elif mode == "reset":
            return Handle(self.connection_id, interface, "RESET")
        
class Handle(Context):
    def __init__(self, connection_id, interface, mode):
        self.opened = False
        Context.__init__(self)
        self.logger = logging.getLogger(str(connection_id, 'ascii'))

        self.check(api.set_interface(self.context, api.INTERFACE[interface]))
        self.check(api.usb_open_string(self.context, connection_id))
        self.opened = True

        self.__eeprom_data_valid = None

        try:
            self.check(api.read_eeprom(self.context))
            self.__eeprom_data_valid = False
            self.check(api.eeprom_decode(self.context, 0))
            self.__eeprom_data_valid = True
        except Exception:
            pass

        if mode == 'SYNCFF':
            assert self.eeprom_value_get("CHANNEL_A_TYPE") == "FIFO" \
                and self.eeprom_value_get("CHANNEL_B_TYPE") == "FIFO"
        
        self.check(api.set_bitmode(self.context, 0, api.BITMODE["RESET"]))
        self.check(api.usb_purge_buffers(self.context))
        self.check(api.set_latency_timer(self.context, 1))
        self.check(api.set_bitmode(self.context, 0, api.BITMODE[mode]))

        self.max_packet_size = self.context.contents.max_packet_size

    def close(self):
        if self.opened:
            self.check(api.usb_close(self.context))
            self.opened = False
        
    def __del__(self):
        self.close()
        Context.__del__(self)
        
    EEPROM_VALUE_MAP = dict(
        CHANNEL_A_TYPE = "CHANNEL_TYPE",
        CHANNEL_B_TYPE = "CHANNEL_TYPE",
        CHANNEL_A_DRIVER = "DRIVER",
        CHANNEL_B_DRIVER = "DRIVER",
        CHANNEL_C_DRIVER = "DRIVER",
        CHANNEL_D_DRIVER = "DRIVER",
        CBUS_FUNCTION_0 = "CBUS",
        CBUS_FUNCTION_1 = "CBUS",
        CBUS_FUNCTION_2 = "CBUS",
        CBUS_FUNCTION_3 = "CBUS",
        CBUS_FUNCTION_4 = "CBUS",
        CBUS_FUNCTION_5 = "CBUS",
        CBUS_FUNCTION_6 = "CBUS",
        CBUS_FUNCTION_7 = "CBUS",
        CBUS_FUNCTION_8 = "CBUS",
        CBUS_FUNCTION_9 = "CBUS",
        GROUP0_DRIVE = "DRIVE",
        GROUP1_DRIVE = "DRIVE",
        GROUP2_DRIVE = "DRIVE",
        GROUP3_DRIVE = "DRIVE",
        CHIP_TYPE = "CHIP_TYPE",
        )


    def eeprom_value_get(self, name):
        if not self.__eeprom_data_valid:
            raise KeyError("No valid eeprom data")

        value = ctypes.c_int()
        id = api.EEPROM_VALUE[name]
        self.check(api.get_eeprom_value(self.context, id, ctypes.byref(value)))
        if name in self.EEPROM_VALUE_MAP:
            
            mapping = getattr(api, self.EEPROM_VALUE_MAP[name] + "_NAME")
            return mapping.get(value.value, value.value)
        else:
            return value.value

    def eeprom_get(self):
        if not self.__eeprom_data_valid:
            raise KeyError("No valid eeprom data")

        raw = (ctypes.c_ubyte * api.MAX_EEPROM_SIZE)()
        self.check(api.get_eeprom_buf(self.context, raw, api.MAX_EEPROM_SIZE))
        return bytes(raw)

    def eeprom_reset_defaults(self, manufacturer, product, serial):
        self.check(api.eeprom_initdefaults(self.context, manufacturer, product, serial))
        self.__eeprom_data_valid = True
        self.eeprom_strings_set(manufacturer, product, serial)

    def eeprom_reset(self):
        self.check(api.erase_eeprom(self.context))
        self.__eeprom_data_valid = True

    def eeprom_strings_set(self, vendor, product, serial):
        if not self.__eeprom_data_valid:
            self.eeprom_reset()
        self.check(api.eeprom_set_strings(self.context, vendor, product, serial))

    def eeprom_vpv_set(self, vid, pid, version = 0):
        if not self.__eeprom_data_valid:
            self.eeprom_reset()
        self.eeprom_value_set("VENDOR_ID", vid)
        self.eeprom_value_set("PRODUCT_ID", pid)
        self.eeprom_value_set("USB_VERSION", version)
        self.eeprom_value_set("USE_USB_VERSION", int(version != 0))

    def eeprom_user_data_set(self, blob):
        eeprom = (ctypes.c_ubyte * 256)()
        self.eeprom_value_set("USER_DATA_ADDR", 0x14)
        self.check(api.get_eeprom_buf(self.context, ctypes.cast(eeprom, ctypes.POINTER(ctypes.c_ubyte)), len(eeprom)))
        ctypes.memmove(ctypes.byref(eeprom, 0x14), blob, len(blob))
        self.check(api.set_eeprom_buf(self.context, ctypes.cast(eeprom, ctypes.POINTER(ctypes.c_ubyte)), len(eeprom)))

    def eeprom_power_set(self, ma = None):
        if not self.__eeprom_data_valid:
            self.eeprom_reset()
        self.eeprom_value_set("SELF_POWERED", int(ma is None))
        self.eeprom_value_set("MAX_POWER", ma)

    def eeprom_channel_mode_set(self, a, b):
        if not self.__eeprom_data_valid:
            self.eeprom_reset()
        self.eeprom_value_set("CHANNEL_A_TYPE", a)
        self.eeprom_value_set("CHANNEL_B_TYPE", b)
            
    def eeprom_writeback(self):
        if not self.__eeprom_data_valid:
            raise RuntimeError("Need valid data to flash EEPROM")
        self.check(api.eeprom_build(self.context))
        self.check(api.write_eeprom(self.context))
        self.check(api.read_eeprom(self.context))

    def eeprom_read_values(self, addr, count):
        values = (ctypes.c_ushort * count)()
        for i in range(count):
            ptr = ctypes.byref(values, ctypes.sizeof(ctypes.c_ushort) * i)
            ptr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort))
            self.check(api.read_eeprom_location(self.context, addr + i, ptr))
        return values[:]
        
    def eeprom_value_set(self, name, value):
        id = api.EEPROM_VALUE[name]

        if name in self.EEPROM_VALUE_MAP:
            mapping = getattr(api, self.EEPROM_VALUE_MAP[name])
            value = mapping.get(value, None)
            if value is None:
                value = int(value)
        else:
            value = int(value)

        self.check(api.set_eeprom_value(self.context, id, value))

    def write(self, blob):
        self.logger.debug("<< %s", binascii.b2a_hex(blob))
        raw = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        self.check(api.write_data(self.context, raw, len(blob)))

    def status(self):
        status = ctypes.c_ushort()
        self.check(api.poll_modem_status(self.context, ctypes.byref(status)))
        return status.value

    def rx_flush(self):
        self.check(api.usb_purge_rx_buffer(self.context))
    
    def _read(self, size = 4096):
        blob = (ctypes.c_ubyte * size)()
        size = self.check(api.read_data(self.context, blob, size))
        return bytes(blob[:size])

    def read(self, rsize):
        ret = bytearray()
        retries = 1000
        while len(ret) < rsize:
            chunk = self._read(rsize - len(ret))
            if chunk:
                retries += 1000
            ret += chunk
            retries -= 1
            if not retries:
                print(">> %s" % binascii.b2a_hex(ret))
                raise base.CommunicationError("Short read, expected %d bytes, had %d" % (rsize, len(ret)))
        self.logger.debug(">> %s", binascii.b2a_hex(ret))
        return ret
    
    def execute(self, blob, rsize = 0):
        try:
            self.write(blob)
        except FtdiError:
            raise FtdiError("Write of %d bytes failed" % len(blob))
        if rsize:
            rsp = self.read(rsize)
            return rsp
        else:
            self.status()

@api.stream_callback_fn
def _callback(buf, size, progress_info, owner):
    if buf and size:
        owner.handle.stream_data(bytes(buf[:size]))

    if progress_info:
        owner.handle.stream_progress(progress_info)
    return int(not owner.running)

class StreamerThread(threading.Thread):
    def __init__(self, handle):
        threading.Thread.__init__(self)
        self.handle = handle
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            blob = self.handle.read(1024)
            if blob:
                self.handle.stream_rx_queue.stream_data(blob)

    def stop(self):
        self.running = False
        self.join()
        
class Ft245SyncFifo(Handle):
    def __init__(self, device, interface, **defaults):
        Handle.__init__(self, device.connection_id, interface, "RESET", **defaults)
        self.stream_rx_queue = queue.Queue()

        self.streamer = StreamerThread(self)
        self.streamer.start()

    def read(self, size):
        ret = bytearray()

        while len(ret) < size:
            ret += self.stream_rx_queue.get()

        return ret

    def stream_data(self, buf):
        self.logger.debug(">> %s", binascii.b2a_hex(buf))
        self.stream_rx_queue.put(buf)

    def stream_progress(self, progress):
        pass

class Mpsse(Handle):
    def __init__(self, device, interface, gpio_oe = 0, gpio_val = 0, **defaults):
        Handle.__init__(self, device.connection_id, interface, "MPSSE", **defaults)

        self.__gpio_oe = gpio_oe
        self.__gpio_val = gpio_val
        self.__freq = 1e6
        
        self.execute(bytes([api.MPSSE_3_PHASE_DISABLE,
                            api.MPSSE_ADAPTIVE_DISABLE,
                            api.MPSSE_LOOPBACK_DISABLE])
                     + self.cmd_gpio_mask_set(0xffff, gpio_oe, gpio_val))

        t = api.CHIP_TYPE_NAME.get(self.context.contents.type, "?")
        self.base_freq = 12e6 if t == "2232C" else 60e6
        self.can_div5 = t != "2232C"
        self.can_opendrain = t == "232H"
        self.cycle_div = 2
        
        self.__divisor = (self.can_div5, 0)
        self.freq = 1e6

    def close(self):
        if self.opened:
            self.gpio_mask_set(0xffff, 0, 0xffff)
        Handle.close(self)
        
    @property
    def last_gpio(self):
        return self.__gpio_oe & self.__gpio_val

    @property
    def freq(self):
        div5, div = self.__divisor
        r = self.base_freq / (div + 1) / self.cycle_div
        if div5:
            r /= 5
        return r

    @freq.setter
    def freq(self, freq):
        cycles = float(freq * self.cycle_div)
        div5 = self.can_div5 and cycles < self.base_freq / 5
        if div5:
            div = math.ceil(self.base_freq / cycles / 5) - 1
        else:
            div = math.ceil(self.base_freq / cycles) - 1

        self.__divisor = div5, min(max(int(div), 0), 0xffff)

        self.logger.debug("freq %s base %s half %s div5 %s div %s -> %s",
                          freq, self.base_freq, self.cycle_div, div5, div, self.freq)

        self.execute(self.cmd_divisor())

    def cmd_divisor(self, divisor = None):
        if divisor is None:
            divisor = self.__divisor
        div5, div = divisor
        div5 = div5
        cmd = b''
        if self.can_div5:
            cmd = bytes([api.MPSSE_CLK_DIV5_ENABLE if div5 else api.MPSSE_CLK_DIV5_DISABLE])
        return cmd + bytes([api.MPSSE_CLK_DIV, div & 0xff, (div & 0xff00) >> 8])

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
        cmd = bytearray()

        self.__gpio_oe = (self.__gpio_oe & ~change_mask) | (change_mask & oe)
        self.__gpio_val = (self.__gpio_val & ~change_mask) | (change_mask & val)

        if change_mask & 0x00ff:
            cmd += bytes([api.MPSSE_SET_BITS_LOW, self.__gpio_val & 0xff, self.__gpio_oe & 0xff])
        if change_mask & 0xff00:
            cmd += bytes([api.MPSSE_SET_BITS_HIGH, (self.__gpio_val >> 8), (self.__gpio_oe >> 8)])

        return cmd
        
    def cmd_gpio_nop(self):
        return bytes([api.MPSSE_SET_BITS_HIGH, (self.__gpio_val >> 8), (self.__gpio_oe >> 8)])

    @classmethod
    def cmd_tms_shift(cls, tms, next = 0):
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS
        ret = bytearray()

        l = len(tms)
        
        for i in range(0, l, 6):
            bits = tms[i : min((i + 7, l))]
            ret += bytes([cmd | api.MPSSE_BITS, len(bits) - 1, int(bits) | (next << 7)])

        return ret

    @classmethod
    def cmd_reset(cls):
        return cls.cmd_tms_shift(BitString(-1, 5))

    @classmethod
    def cmd_run(cls, count):
        return cls.cmd_tms_shift(BitString(0, count))

    @classmethod
    def cmd_ir(cls):
        return cls.cmd_tms_shift(BitString(0b01011, 5))

    @classmethod
    def cmd_dr(cls):
        return cls.cmd_tms_shift(BitString(0b0101, 4))

    @classmethod
    def cmd_update(cls):
        return cls.cmd_tms_shift(BitString(0b011, 3))

    @classmethod
    def cmd_shift_io(cls, tdi):
        if not len(tdi):
            return b'', []

        counts = []
        tms_cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS | api.MPSSE_BITS
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE
        read = api.MPSSE_READ

        ret = bytearray()
        
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

    @classmethod
    def cmd_shift_out(cls, tdi):
        if not len(tdi):
            return b''

        tms_cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_TMS | api.MPSSE_BITS
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE

        ret = bytearray()
        
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

    @classmethod
    def cmd_out(cls, tdi):
        if not len(tdi):
            return b''
        
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_LSB | api.MPSSE_WRITE

        ret = bytearray()
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

    @classmethod
    def cmd_in(cls, bits):
        if not bits:
            return b''

        counts = []

        cmd = api.MPSSE_LSB | api.MPSSE_READ

        ret = bytearray()
        
        if bits >= 8:
            ret += struct.pack("<BH", cmd, (bits // 8) - 1)
            counts.append((bits // 8, None))

        if bits % 8:
            ret += bytes([cmd | api.MPSSE_BITS, (bits % 8) - 1])
            counts.append((1, bits % 8))
        
        return ret, counts

    @classmethod
    def cmd_out_be(cls, tdi):
        if not len(tdi):
            return b''
        
        cmd = api.MPSSE_WRITE_NEG | api.MPSSE_WRITE

        ret = bytearray()
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

    @classmethod
    def cmd_in_be(cls, bits):
        if not bits:
            return b''

        counts = []

        cmd = api.MPSSE_READ

        ret = bytearray()
        
        if bits >= 8:
            ret += struct.pack("<BH", cmd, (bits // 8) - 1)
            counts.append((bits // 8, None))

        if bits % 8:
            ret += bytes([cmd | api.MPSSE_BITS, (bits % 8) - 1])
            counts.append((1, bits % 8))
        
        return ret, counts

    @classmethod
    def cmd_idle(cls, cycles, value):
        assert cycles

        return cls.cmd_out(BitString(-value, cycles))
        
def main():
    import time
    adapters = Device.list_all(0x10eb, 0x26)
    mpsse = adapters[0].open()
#    mpsse.gpio_mask_set(0xffff, 0x60eb, 0x00e8)
#
#    mpsse.freq = 1000
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
