from . import api
from ... import model
import os
import binascii
import ctypes
import struct
import sys
import math
import logging

__all__ = ["JaylinkError", "Handle", "Device", "Context"]

class JaylinkError(Exception):
    def __init__(self, message, code):
        Exception.__init__(self, message)
        self.code = code

def checked(err):
    if err != api.OK:
        msg = str(api.strerror(err), 'utf-8')
        raise JaylinkError(msg, err)

class Handle(model.Component):
    def __init__(self, handle, context):
        model.Component.__init__(self, "JLink handle")
        self.handle = handle
        self.context = context
        self.caps = self._get_caps()
        self._close = api.close
        self.__resetn = None
        self.__tresetn = None
        self.__target_power = None
        self.__speed = 1000

        if "REGISTER" in self.caps:
            self._register()

        self.interface

    def _register(self):
        self.register_conn = api.connection()

        self.register_conn.handle = 0
        self.register_conn.pid = os.getpid()
        self.register_conn.hid = b"0.0.0.0"
        self.register_conn.iid = 0
        self.register_conn.cid = 0
        
        self.register_conns = (api.connection * api.MAX_CONNECTIONS)()
        ctypes.memset(self.register_conns, 0, ctypes.sizeof(self.register_conns))
        self.register_count = ctypes.c_size_t(0)

        checked(api.register(self.handle, ctypes.byref(self.register_conn),
                                    self.register_conns, ctypes.byref(self.register_count)))

        self.__unregister = api.unregister

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
        d = api.get_device(self.handle)
        ret = Device(d)
        api.unref_device(d)
        return ret

    @property
    def firmware_version(self):
        value = ctypes.c_char_p()
        length = ctypes.c_size_t()

        checked(api.get_firmware_version(self.handle, ctypes.byref(value), ctypes.byref(length)))
        return [str(x, 'utf-8') for x in ctypes.string_at(value, length.value).split(b"\x00")[:2]]

    @property
    def hardware_version(self):
        if not "GET_HW_VERSION" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = api.hardware_version()
        checked(api.get_hardware_version(self.handle, ctypes.byref(value)))
        return value.type, value.major, value.minor, value.revision

    @property
    def hardware_status(self):
        value = api.hardware_status()
        checked(api.get_hardware_status(self.handle, ctypes.byref(value)))
        return value

    def _get_caps(self):
        caps = (ctypes.c_ubyte * api.DEV_EXT_CAPS_SIZE)()
        ctypes.memset(caps, 0, api.DEV_EXT_CAPS_SIZE)

        checked(api.get_caps(self.handle, caps))

        if caps[api.DEV_CAP["GET_EXT_CAPS"] >> 3] & (1 << (api.DEV_CAP["GET_EXT_CAPS"] & 0x7)):
            checked(api.get_extended_caps(self.handle, caps))

        ret = set([api.DEV_CAP_NAME.get(i, "CAP_%d" % i)
                   for i in range(api.DEV_EXT_CAPS_SIZE * 8)
                   if ((caps[i >> 3] >> (i & 0x7)) & 1)])
        return ret

    @property
    def free_memory(self):
        if not "GET_FREE_MEMORY" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = ctypes.c_uint32()
        checked(api.get_free_memory(self.handle, ctypes.byref(value)))
        return value.value

    @property
    def config(self):
        if not "READ_CONFIG" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = (ctypes.c_ubyte * api.DEV_CONFIG_SIZE)()
        checked(api.read_raw_config(self.handle, ctypes.cast(value, ctypes.POINTER(ctypes.c_ubyte))))
        return bytes(value)

    @config.setter
    def config(self, value):
        if not "WRITE_CONFIG" in self.caps:
            raise NotImplementedError("Incapable hardware")

        value = (ctypes.c_ubyte * api.DEV_CONFIG_SIZE).from_buffer_copy(value)
        checked(api.write_raw_config(self.handle, value))

    @property
    def available_interfaces(self):
        intf = ctypes.c_uint32()

        checked(api.get_available_interfaces(self.handle, ctypes.byref(intf)))
        return set([name for name, no in api.TIF.items() if ((intf.value >> no) & 1)])

    # file_read
    # file_write
    # file_get_size
    # file_delete

    def hardware_info_get(self, name):
        if "GET_HW_INFO" not in self.caps:
            raise NotImplementedError("Incapable hardware")
            
        value = ctypes.c_int32()
        
        checked(api.get_hardware_info(self.handle, api.HW_INFO[name], ctypes.byref(value)))
        return value.value

    def counter_get(self, name):
        if "GET_COUNTERS" not in self.caps:
            raise NotImplementedError("Incapable hardware")
            
        value = ctypes.c_int32()
        
        checked(api.get_hardware_info(self.handle, api.COUNTER_TARGET[name], ctypes.byref(value)))
        return value.value

    def emucom_read(self, channel, size):
        buffer = ctypes.create_string_buffer(size)
        size_ = ctypes.c_uint32(size)
        
        checked(api.emucom_read(self.handle, channel, buffer, ctypes.byref(size_)))
        return ctypes.string_at(buffer, size_.value)

    def emucom_write(self, channel, data):
        buffer = (ctypes.c_char * len(data)).from_buffer_copy(data)
        size_ = ctypes.c_uint32(len(data))

        checked(api.emucom_write(self.handle, channel, buffer, ctypes.byref(size_)))
        return size_.value

    def jtag_io(self, tms, tdi, count):
        assert self.__interface == "JTAG"

        length = (count + 7) // 8
        tms_buf = (ctypes.c_ubyte * length).from_buffer_copy(tms)
        tdi_buf = (ctypes.c_ubyte * length).from_buffer_copy(tdi)
        tdo_buf = (ctypes.c_ubyte * length)()

        checked(api.jtag_io(self.handle, tms_buf, tdi_buf, tdo_buf, count, 1))

        return bytes(tdo_buf)

    @property
    def tresetn(self):
        return self.__tresetn

    @tresetn.setter
    def tresetn(self, value):
        self.__tresetn = bool(value)
        if value:
            checked(api.jtag_set_trst(self.handle))
        else:
            checked(api.jtag_clear_trst(self.handle))
            
    def swd_io(self, out, oe, count):
        assert self.__interface == "SWD"

        length = (count + 7) // 8
        out_buf = (ctypes.c_ubyte * length).from_buffer_copy(out)
        oe_buf = (ctypes.c_ubyte * length).from_buffer_copy(oe)
        input_buf = (ctypes.c_ubyte * length)()

        checked(api.swd_io(self.handle, oe_buf, out_buf, input_buf, count))

        return bytes(bytearray(input_buf))

    @property
    def speed(self):
        return self.__speed

    @speed.setter
    def speed(self, khz):
        speed = api.speed()
        checked(api.get_speeds(self.handle, ctypes.byref(speed)))
        if khz:
            div = max((int(speed.freq / (khz * 1000.) + .5), speed.div))
        else:
            div = speed.div

        self.__speed = int(speed.freq / div / 1000. + .5)

        self.logger.info("requested speed %d kHz, had %dHz/%d (%d kHz)", khz, speed.freq, div, self.__speed)
        
        checked(api.set_speed(self.handle, self.__speed))

    @property
    def speed_range(self):
        value = api.speed()
        checked(api.get_speeds(self.handle, ctypes.byref(value)))
        return (1000, value.freq / value.div)

    @property
    def interface(self):
        interface = api.target_interface()
        checked(api.get_selected_interface(self.handle, ctypes.byref(interface)))
        self.__interface = api.TIF_NAME[interface.value]
        return self.__interface

    @interface.setter
    def interface(self, interface):
        checked(api.select_interface(self.handle, api.TIF[interface], None))
        assert self.interface == interface
        self.speed = self.__speed

    @property
    def resetn(self):
        return self.__resetn

    @resetn.setter
    def resetn(self, value):
        self.__resetn = bool(value)
        if value:
            checked(api.set_reset(self.handle))
        else:
            checked(api.clear_reset(self.handle))

    @property
    def power(self):
        return self.__target_power

    @power.setter
    def power(self, enabled):
        if "SET_TARGET_POWER" not in self.caps:
            raise NotImplementedError("Incapable hardware")
        self.__target_power = bool(enabled)
        checked(api.set_target_power(self.handle, bool(enabled)))

    # swo_start
    # swo_stop
    # swo_read
    # swo_get_speeds

class Device(object):
    def __init__(self, device, context):
        self.device = api.ref_device(device)
        self.context = context
        self.unref = api.unref_device

    def __del__(self):
        #self.unref(self.device)
        pass

    def open(self):
        handle = ctypes.POINTER(api.device_handle)()
        checked(api.open(self.device, ctypes.byref(handle)))
        return Handle(handle, self.context)
    
    @property
    def host_interface(self):
        intf = api.host_interface()
        checked(api.device_get_host_interface(self.device, ctypes.byref(intf)))
        return api.HIF_NAME[int(math.log(intf.value, 2))]

    @property
    def serial_number(self):
        serial = ctypes.c_int32()
        checked(api.device_get_serial_number(self.device, ctypes.byref(serial)))
        return serial.value

    @property
    def usb_address(self):
        usb_addr = api.usb_address()
        checked(api.device_get_usb_address(self.device, ctypes.byref(usb_addr)))
        return usb_addr.value

if sys.platform == "darwin":
    _vsnprintf = ctypes.CDLL("libc.dylib").vsnprintf
else:
    _vsnprintf = ctypes.CDLL("libc.so.6").vsnprintf
_vsnprintf.argstypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_void_p]
_vsnprintf.restype = ctypes.c_ssize_t

class Context(object):
    def __init__(self):
        self.context = ctypes.POINTER(api.context)()
        checked(api.init(ctypes.byref(self.context)))
        self.exit = api.exit
        checked(api.log_set_callback(self.context, self._log,
                                            ctypes.py_object(self)))

        self.logger = logging.getLogger("jaylink")
        self.log_level_match = {}
        for name, level in [("DEBUG", logging.DEBUG),
                            ("INFO", logging.INFO),
                            ("WARNING", logging.WARNING),
                            ("ERROR", logging.ERROR)]:
            self.log_level_match[api.LOG_LEVEL[name]] = level
        
    @staticmethod
    @api.log_callback
    def _log(ctx, level, format, args, self):
        if not _vsnprintf or not ctypes or not level:
            return 0
        formatted = ctypes.create_string_buffer(4096)
        _vsnprintf(formatted, 4096, format, ctypes.c_void_p(args))
        self.logger.log(self.log_level_match[level], str(formatted.value, "utf-8"))
        return 0

    def __del__(self):
        self.exit(self.context)
        pass

    def devices(self):
        checked(api.discovery_scan(self.context, api.HIF["USB"]))
        
        devices = ctypes.POINTER(ctypes.POINTER(api.device))()

        checked(api.get_devices(self.context, ctypes.byref(devices), None))
        
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

        api.free_devices(devices, True)
        
        return ret

    def open(self, serial):
        for d in self.devices():
            if d.serial_number == serial:
                return d.open()
        raise KeyError("No such device %d" % serial)

    @property
    def log_level(self):
        level = api.log_level()
        checked(api.log_get_level(self.context, ctypes.byref(level)))
        return level.value

    @log_level.setter
    def log_level(self, level):
        checked(api.log_set_level(self.context, level))

    @property
    def log_domain(self):
        domain = api.log_domain()
        checked(api.log_get_domain(self.context, ctypes.byref(domain)))
        return domain.value

    @log_domain.setter
    def log_domain(self, domain):
        checked(api.log_set_domain(self.context, domain))

    @classmethod
    def serial_number_parse(cls, serial):
        ret = ctypes.c_int32()
        checked(api.parse_serial_number(serial, ctypes.byref(ret)))
        return ret.value

    @property
    def package_version(cls):
        s = api.version_package_get_string()
        return str(s)

    @property
    def library_version(cls):
        s = api.version_library_get_string()
        return str(s)

if __name__ == "__main__":
    ctx = Context()

    print(ctx.package_version)
    print(ctx.library_version)

    ctx.log_level = api.LOG_LEVEL["NONE"]

    for d in ctx.devices():
        print(d.serial_number, d.host_interface)
        h = d.open()
        print("hw:", repr(h.hardware_version))
        print("fw:", repr(h.firmware_version))
        print(h.caps)

        if "GET_HW_INFO" in h.caps:
            for name in api.HW_INFO.keys():
                try:
                    v = h.hardware_info_get(name)
                    print(name, v)
                except:
                    pass

        if "GET_COUNTERS" in h.caps:
            for name in api.COUNTER_TARGET.keys():
                try:
                    v = h.counter_get(name)
                    print(name, v)
                except:
                    pass

        if "READ_CONFIG" in h.caps:
            print(binascii.b2a_hex(h.config))
            
        for i in h.available_interfaces:
            h.interface = i
            print(i, h.speed_range)

        h.power = False
