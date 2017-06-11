from . import libjaylink
import os
import binascii
import ctypes
import struct
import sys
import math

class JaylinkError(Exception):
    def __init__(self, message, code):
        Exception.__init__(self, message)
        self.code = code

def checked(err):
    if err != libjaylink.OK:
        msg = libjaylink.strerror(err)
        raise JaylinkError(msg, err)
    return err

class Handle(object):
    def __init__(self, handle, context):
        self.handle = handle
        self.context = context
        self.caps = self._get_caps()
        self._close = libjaylink.close
        self.__resetn = None
        self.__trst = None
        self.__target_power = None

        if "REGISTER" in self.caps:
            self._register()

        self.interface

    def _register(self):
        self.register_conn = libjaylink.connection()

        self.register_conn.handle = 0
        self.register_conn.pid = os.getpid()
        self.register_conn.hid = "0.0.0.0"
        self.register_conn.iid = 0
        self.register_conn.cid = 0
        
        self.register_conns = (libjaylink.connection * libjaylink.MAX_CONNECTIONS)()
        ctypes.memset(self.register_conns, 0, ctypes.sizeof(self.register_conns))
        self.register_count = ctypes.c_size_t(0)

        checked(libjaylink.register(self.handle, ctypes.byref(self.register_conn),
                                    self.register_conns, ctypes.byref(self.register_count)))

        self.__unregister = libjaylink.unregister

        for i in range(self.register_count.value):
            if self.register_conns[i].handle == self.register_conn.handle:
                return

        raise RuntimeError("Registration failed")

    def _unregister(self):
        checked(self.__unregister(self.handle, ctypes.byref(self.register_conn),
                                  self.register_conns, ctypes.byref(self.register_count)))

    def __del__(self):
        if "REGISTER" in self.caps:
            self._unregister()
        self._close(self.handle)

    @property
    def device(self):
        d = libjaylink.get_device(self.handle)
        ret = Device(d)
        libjaylink.unref_device(d)
        return ret

    @property
    def firmware_version(self):
        value = ctypes.c_char_p()
        length = ctypes.c_size_t()

        checked(libjaylink.get_firmware_version(self.handle, ctypes.byref(value), ctypes.byref(length)))
        return ctypes.string_at(value, length.value).split("\x00")[:2]

    @property
    def hardware_version(self):
        if not "GET_HW_VERSION" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = libjaylink.hardware_version()
        checked(libjaylink.get_hardware_version(self.handle, ctypes.byref(value)))
        return value.type, value.major, value.minor, value.revision

    @property
    def hardware_status(self):
        value = libjaylink.hardware_status()
        checked(libjaylink.get_hardware_status(self.handle, ctypes.byref(value)))
        return value

    def _get_caps(self):
        caps = (ctypes.c_ubyte * libjaylink.DEV_EXT_CAPS_SIZE)()
        ctypes.memset(caps, 0, libjaylink.DEV_EXT_CAPS_SIZE)

        checked(libjaylink.get_caps(self.handle, caps))

        if caps[libjaylink.DEV_CAP["GET_EXT_CAPS"] >> 3] & (1 << (libjaylink.DEV_CAP["GET_EXT_CAPS"] & 0x7)):
            checked(libjaylink.get_extended_caps(self.handle, caps))

        ret = set([libjaylink.DEV_CAP_NAME.get(i, "CAP_%d" % i)
                   for i in range(libjaylink.DEV_EXT_CAPS_SIZE * 8)
                   if ((caps[i >> 3] >> (i & 0x7)) & 1)])
        return ret

    @property
    def free_memory(self):
        if not "GET_FREE_MEMORY" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = ctypes.c_uint32()
        checked(libjaylink.get_free_memory(self.handle, ctypes.byref(value)))
        return value.value

    @property
    def config(self):
        if not "READ_CONFIG" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = (ctypes.c_char * libjaylink.DEV_CONFIG_SIZE)()
        checked(libjaylink.read_raw_config(self.handle, ctypes.cast(value, ctypes.POINTER(ctypes.c_ubyte))))
        return str(value.raw)

    @config.setter
    def config(self, value):
        if not "WRITE_CONFIG" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = (ctypes.c_uint8 * libjaylink.DEV_CONFIG_SIZE).from_buffer_copy(value)
        checked(libjaylink.write_raw_config(self.handle, value))

    @property
    def available_interfaces(self):
        intf = ctypes.c_uint32()

        checked(libjaylink.get_available_interfaces(self.handle, ctypes.byref(intf)))
        return set([name for name, no in libjaylink.TIF.items() if ((intf.value >> no) & 1)])

    # file_read
    # file_write
    # file_get_size
    # file_delete

    def hardware_info_get(self, name):
        if "GET_HW_INFO" not in self.caps:
            raise NotImplementedError("Incapable hardware")
            
        value = ctypes.c_int32()
        
        checked(libjaylink.get_hardware_info(self.handle, libjaylink.HW_INFO[name], ctypes.byref(value)))
        return value.value

    def counter_get(self, name):
        if "GET_COUNTERS" not in self.caps:
            raise NotImplementedError("Incapable hardware")
            
        value = ctypes.c_int32()
        
        checked(libjaylink.get_hardware_info(self.handle, libjaylink.COUNTER_TARGET[name], ctypes.byref(value)))
        return value.value

    def emucom_read(self, channel, size):
        buffer = ctypes.create_string_buffer(size)
        size_ = ctypes.c_uint32(size)
        
        checked(libjaylink.emucom_read(self.handle, channel, buffer, ctypes.byref(size_)))
        return ctypes.string_at(buffer, size_.value)

    def emucom_write(self, channel, data):
        buffer = (ctypes.c_char * len(data)).from_buffer_copy(data)
        size_ = ctypes.c_uint32(len(data))

        checked(libjaylink.emucom_write(self.handle, channel, buffer, ctypes.byref(size_)))
        return size_.value

    def jtag_io(self, tms, tdi, count):
        assert self.__interface == "JTAG"

        length = (count + 7) / 8
            
        if isinstance(tms, (int, long)):
            tms_buf = (ctypes.c_char * length)()
            for i in range(length):
                tms_buf[i] = chr((tms >> (i * 8)) & 0xff)
        else:
            tms_buf = (ctypes.c_char * length).from_buffer_copy(tms.ljust(length, "\x00"))

        if isinstance(tdi, (int, long)):
            tdi_buf = (ctypes.c_char * length)()
            for i in range(length):
                tdi_buf[i] = chr((tdi >> (i * 8)) & 0xff)
        else:
            tdi_buf = (ctypes.c_char * length).from_buffer_copy(tdi.ljust(length, "\x00"))

        tdo_buf = (ctypes.c_char * length)()

        checked(libjaylink.jtag_io(self.handle, tms_buf, tdi_buf, tdo_buf,
                                   count, 2))

        if isinstance(tdi, (int, long)):
            tdo = 0
            for i in range(length):
                tdo |= ord(tdo_buf[i]) << (8 * i)
            return tdo
        else:
            return str(bytearray(tdo_buf))[:length]

    @property
    def trst(self):
        return self.__trst

    @trst.setter
    def trst(self, value):
        self.__trst = bool(value)
        if value:
            checked(libjaylink.jtag_set_trst(self.handle))
        else:
            checked(libjaylink.jtag_clear_trst(self.handle))
            
    def swd_io(self, out, oe, count):
        assert self.__interface == "SWD"

        length = (count + 7) / 8

        if isinstance(out, (int, long)):
            out_buf = (ctypes.c_ubyte * length)()
            for i in range(length):
                out_buf[i] = chr((out >> (i * 8)) & 0xff)
        else:
            out_buf = (ctypes.c_ubyte * length).from_buffer_copy(out.ljust(length, "\x00"))
            
        if isinstance(oe, (int, long)):
            oe_buf = (ctypes.c_ubyte * length)()
            for i in range(length):
                oe_buf[i] = chr((oe >> (i * 8)) & 0xff)
        else:
            oe_buf = (ctypes.c_ubyte * length).from_buffer_copy(oe.ljust(length, "\x00"))

        input_buf = (ctypes.c_ubyte * length)()

        checked(libjaylink.swd_io(self.handle, oe_buf, out_buf, input_buf, count))

        if isinstance(out, (int, long)):
            input = 0
            for i in range(length):
                input |= ord(input_buf[i]) << (8 * i)
            return input
        else:
            return str(bytearray(input_buf))[:length]

    @property
    def speed(self):
        return self.__speed

    @speed.setter
    def speed(self, khz):
        speed = libjaylink.speed()
        checked(libjaylink.get_speeds(self.handle, ctypes.byref(speed)))
        div = max((int(speed.freq / (khz * 1000.) + .5), speed.div))

        self.__speed = int(speed.freq / div / 1000. + .5)
        
        checked(libjaylink.set_speed(self.handle, self.__speed))

    @property
    def speed_range(self):
        value = libjaylink.speed()
        checked(libjaylink.get_speeds(self.handle, ctypes.byref(value)))
        return (1000, value.freq / value.div)

    @property
    def interface(self):
        interface = libjaylink.target_interface()
        checked(libjaylink.get_selected_interface(self.handle, ctypes.byref(interface)))
        self.__interface = libjaylink.TIF_NAME[interface.value]
        return self.__interface

    @interface.setter
    def interface(self, interface):
        checked(libjaylink.select_interface(self.handle, libjaylink.TIF[interface], None))
        self.interface

    @property
    def resetn(self):
        return self.__resetn

    @resetn.setter
    def resetn(self, value):
        self.__resetn = bool(value)
        if value:
            checked(libjaylink.set_reset(self.handle))
        else:
            checked(libjaylink.clear_reset(self.handle))

    @property
    def power(self):
        return self.__target_power

    @power.setter
    def power(self, enabled):
        self.__target_power = bool(enabled)
        checked(libjaylink.set_target_power(self.handle, bool(enabled)))

    # swo_start
    # swo_stop
    # swo_read
    # swo_get_speeds

class Device(object):
    def __init__(self, device, context):
        self.device = libjaylink.ref_device(device)
        self.context = context
        self.unref = libjaylink.unref_device

    def __del__(self):
        self.unref(self.device)

    def open(self):
        handle = ctypes.POINTER(libjaylink.device_handle)()
        checked(libjaylink.open(self.device, ctypes.byref(handle)))
        return Handle(handle, self.context)

    @property
    def host_interface(self):
        intf = libjaylink.host_interface()
        checked(libjaylink.device_get_host_interface(self.device, ctypes.byref(intf)))
        return libjaylink.HIF_NAME[int(math.log(intf.value, 2))]

    @property
    def serial_number(self):
        serial = ctypes.c_int32()
        checked(libjaylink.device_get_serial_number(self.device, ctypes.byref(serial)))
        return serial.value

    @property
    def usb_address(self):
        usb_addr = libjaylink.usb_address()
        checked(libjaylink.device_get_usb_address(self.device, ctypes.byref(usb_addr)))
        return usb_addr.value

if sys.platform == "darwin":
    _vsnprintf = ctypes.CDLL("libc.dylib").vsnprintf
else:
    _vsnprintf = ctypes.CDLL("libc.so.6").vsnprintf
_vsnprintf.argstypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_void_p]
_vsnprintf.restype = ctypes.c_ssize_t

class Context(object):
    def __init__(self):
        self.context = ctypes.POINTER(libjaylink.context)()
        checked(libjaylink.init(ctypes.byref(self.context)))
        self.exit = libjaylink.exit
        checked(libjaylink.log_set_callback(self.context, self._log,
                                            ctypes.py_object(self)))

    @staticmethod
    @libjaylink.log_callback
    def _log(ctx, level, format, args, self):
        if not _vsnprintf or not ctypes:
            return 0
        formatted = ctypes.create_string_buffer(4096)
        _vsnprintf(formatted, 4096, format, ctypes.c_void_p(args))
        if level < libjaylink.LOG_LEVEL["DEBUG"]:
            print formatted.value
        return 0

    def __del__(self):
        self.exit(self.context)
        pass

    def devices(self):
        checked(libjaylink.discovery_scan(self.context, libjaylink.HIF["USB"]))
        
        devices = ctypes.POINTER(ctypes.POINTER(libjaylink.device))()

        checked(libjaylink.get_devices(self.context, ctypes.byref(devices), None))
        
        ret = []
        i = 0
        while devices[i]:
            d = Device(devices[i], self)
            try:
                d.serial_number
            except:
                break
            ret.append(d)
            i += 1

        libjaylink.free_devices(devices, True)
        
        return ret

    def open(self, serial):
        for d in self.devices():
            if d.serial_number == serial:
                return d.open()
        raise KeyError("No such device %d" % serial)

    @property
    def log_level(self):
        level = libjaylink.log_level()
        checked(libjaylink.log_get_level(self.context, ctypes.byref(level)))
        return level.value

    @log_level.setter
    def log_level(self, level):
        checked(libjaylink.log_set_level(self.context, level))

    @property
    def log_domain(self):
        domain = libjaylink.log_domain()
        checked(libjaylink.log_get_domain(self.context, ctypes.byref(domain)))
        return domain.value

    @log_domain.setter
    def log_domain(self, domain):
        checked(libjaylink.log_set_domain(self.context, domain))

    @classmethod
    def serial_number_parse(cls, serial):
        ret = ctypes.c_int32()
        checked(libjaylink.parse_serial_number(serial, ctypes.byref(ret)))
        return ret.value

    @property
    def package_version(cls):
        s = libjaylink.version_package_get_string()
        return str(s)

    @property
    def library_version(cls):
        s = libjaylink.version_library_get_string()
        return str(s)

if __name__ == "__main__":
    ctx = Context()

    print ctx.package_version
    print ctx.library_version

#    print ctx.log_level
#    ctx.log_level = libjaylink.LOG_LEVEL_DEBUG
    ctx.log_level = libjaylink.LOG_LEVEL["NONE"]

    for d in ctx.devices():
        print d.serial_number, d.host_interface
        h = d.open()
        print "hw:", repr(h.hardware_version)
        print "fw:", repr(h.firmware_version)
        print h.caps

        if "GET_HW_INFO" in h.caps:
            for name in libjaylink.HW_INFO.keys():
                try:
                    v = h.hardware_info_get(name)
                    print name, v
                except:
                    pass

        if "GET_COUNTERS" in h.caps:
            for name in libjaylink.COUNTER_TARGET.keys():
                try:
                    v = h.counter_get(name)
                    print name, v
                except:
                    pass

        if "READ_CONFIG" in h.caps:
            print binascii.b2a_hex(h.config)
            
        for i in h.available_interfaces:
            h.interface = i
            print i, h.speed_range

        h.power = False
