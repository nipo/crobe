import ctypes as _c
from ...util.dynamic_library import load as _load

_lib = _load("jaylink", 0)

error = _c.c_int
OK = 0
ERR = (-1)
ERR_ARG = (-2)
ERR_MALLOC = (-3)
ERR_TIMEOUT = (-4)
ERR_PROTO = (-5)
ERR_NOT_AVAILABLE = (-6)
ERR_NOT_SUPPORTED = (-7)
ERR_IO = (-8)
ERR_DEV = (-1000)
ERR_DEV_NOT_SUPPORTED = (-1001)
ERR_DEV_NOT_AVAILABLE = (-1002)
ERR_DEV_NO_MEMORY = (-1003)

log_level = _c.c_int
LOG_LEVEL = dict(
    NONE = 0,
    ERROR = 1,
    WARNING = 2,
    INFO = 3,
    DEBUG = 4,
)

capability = _c.c_int
CAP = dict(
    HIF_USB = 0,
)

host_interface = _c.c_int
HIF = dict(
    USB = 0,
)
HIF_NAME = dict([(v, k) for (k, v) in HIF.items()])

usb_address = _c.c_int

device_capability = _c.c_int
DEV_CAP = dict(
    GET_HW_VERSION = 1,
    WRITE_DCC = 2,
    ADAPTIVE_CLOCKING = 3,
    READ_CONFIG = 4,
    WRITE_CONFIG = 5,
    TRACE = 6,
    WRITE_MEM = 7,
    READ_MEM = 8,
    GET_SPEEDS = 9,
    EXEC_CODE = 10,
    GET_FREE_MEMORY = 11,
    GET_HW_INFO = 12,
    SET_TARGET_POWER = 13,
    RESET_STOP_TIMED = 14,
    MEASURE_RTCK_REACT = 16,
    SELECT_TIF = 17,
    RW_MEM_ARM79 = 18,
    GET_COUNTERS = 19,
    READ_DCC = 20,
    GET_CPU_CAPS = 21,
    EXEC_CPU_CMD = 22,
    SWO = 23,
    WRITE_DCC_EX = 24,
    UPDATE_FIRMWARE_EX = 25,
    FILE_IO = 26,
    REGISTER = 27,
    INDICATORS = 28,
    TEST_NET_SPEED = 29,
    RAWTRACE = 30,
    GET_EXT_CAPS = 31,
    JTAG_WRITE = 32,
    EMUCOM = 33,
    ETHERNET = 38,
)
DEV_CAP_NAME = dict([(v, k) for (k, v) in DEV_CAP.items()])

hardware_info = _c.c_int
HW_INFO = dict(
    TARGET_POWER = 0,
    POWER_OVERCURRENT = 1,
    ITARGET = 2,
    ITARGET_PEAK = 3,
    ITARGET_PEAK_OPERATION = 4,
    ITARGET_MAX_TIME0 = 10,
    ITARGET_MAX_TIME1 = 11,
    ITARGET_MAX_TIME2 = 12,
)

counter = _c.c_int
COUNTER_TARGET = dict(
    TIME = 0,
    CONNECTIONS = 1,
)

hardware_type = _c.c_int
HW_TYPE = dict(
    JLINK = 0,
    FLASHER = 2,
    JLINK_PRO = 3,
)

target_interface = _c.c_int
TIF = dict(
    JTAG = 0,
    SWD = 1,
    BDM3 = 2,
    FINE = 3,
    CJTAG_PIC32 = 4,
)
TIF_NAME = dict([(v, k) for (k, v) in TIF.items()])

jtag_version = _c.c_int

swo_mode = _c.c_int
SWO_MODE = dict(
    UART = 0,
)

class speed(_c.Structure):
    _fields_ = [
        ('freq', _c.c_uint32),
        ('div', _c.c_uint16),
        ]
    __slots__ = [x[0] for x in _fields_]

class swo_speed(_c.Structure):
    _fields_ = [
        ('freq', _c.c_uint32),
        ('min_div', _c.c_uint32),
        ('max_div', _c.c_uint32),
        ('min_prescaler', _c.c_uint32),
        ('max_prescaler', _c.c_uint32),
        ]
    __slots__ = [x[0] for x in _fields_]

class hardware_version(_c.Structure):
    _fields_ = [
        ('type', hardware_type),
        ('major', _c.c_uint8),
        ('minor', _c.c_uint8),
        ('revision', _c.c_uint8),
        ]
    __slots__ = [x[0] for x in _fields_]

class hardware_status(_c.Structure):
    _fields_ = [
        ('target_voltage', _c.c_uint16),
        ('tck', _c.c_bool),
        ('tdi', _c.c_bool),
        ('tdo', _c.c_bool),
        ('tms', _c.c_bool),
        ('tres', _c.c_bool),
        ('trst', _c.c_bool),
        ]
    __slots__ = [x[0] for x in _fields_]

class connection(_c.Structure):
    _fields_ = [
        ('handle', _c.c_uint16),
        ('pid', _c.c_uint32),
        ('hid', _c.c_char * 16),
        ('iid', _c.c_uint8),
        ('cid', _c.c_uint8),
        ('timestamp', _c.c_uint32),
        ]
    __slots__ = [x[0] for x in _fields_]

class context(_c.Structure):
    pass

context_ptr = _c.POINTER(context)

class device(_c.Structure):
    pass

class device_handle(_c.Structure):
    pass

log_callback = _c.CFUNCTYPE(_c.c_int, _c.POINTER(context), log_level, _c.c_char_p, _c.c_void_p, _c.py_object)

init = _lib.jaylink_init
init.argtypes = [_c.POINTER(_c.POINTER(context))]
init.restype = _c.c_int

exit = _lib.jaylink_exit
exit.argtypes = [_c.POINTER(context)]
exit.restype = _c.c_int

library_has_cap = _lib.jaylink_library_has_cap
library_has_cap.argtypes = [capability]
library_has_cap.restype = _c.c_bool

get_devices = _lib.jaylink_get_devices
get_devices.argtypes = [_c.POINTER(context), _c.POINTER(_c.POINTER(_c.POINTER(device))), _c.POINTER(_c.c_size_t)]
get_devices.restype = _c.c_int

free_devices = _lib.jaylink_free_devices
free_devices.argtypes = [_c.POINTER(_c.POINTER(device)), _c.c_bool]
free_devices.restype = None

device_get_host_interface = _lib.jaylink_device_get_host_interface
device_get_host_interface.argtypes = [_c.POINTER(device), _c.POINTER(host_interface)]
device_get_host_interface.restype = _c.c_int

device_get_serial_number = _lib.jaylink_device_get_serial_number
device_get_serial_number.argtypes = [_c.POINTER(device), _c.POINTER(_c.c_int32)]
device_get_serial_number.restype = _c.c_int

device_get_usb_address = _lib.jaylink_device_get_usb_address
device_get_usb_address.argtypes = [_c.POINTER(device), _c.POINTER(usb_address)]
device_get_usb_address.restype = _c.c_int

ref_device = _lib.jaylink_ref_device
ref_device.argtypes = [_c.POINTER(device)]
ref_device.restype = _c.POINTER(device)

unref_device = _lib.jaylink_unref_device
unref_device.argtypes = [_c.POINTER(device)]
unref_device.restype = None

open = _lib.jaylink_open
open.argtypes = [_c.POINTER(device), _c.POINTER(_c.POINTER(device_handle))]
open.restype = _c.c_int

close = _lib.jaylink_close
close.argtypes = [_c.POINTER(device_handle)]
close.restype = _c.c_int

get_device = _lib.jaylink_get_device
get_device.argtypes = [_c.POINTER(device_handle)]
get_device.restype = _c.POINTER(device)

get_firmware_version = _lib.jaylink_get_firmware_version
get_firmware_version.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_char_p), _c.POINTER(_c.c_size_t)]
get_firmware_version.restype = _c.c_int

get_hardware_info = _lib.jaylink_get_hardware_info
get_hardware_info.argtypes = [_c.POINTER(device_handle), _c.c_uint32, _c.POINTER(_c.c_int32)]
get_hardware_info.restype = _c.c_int

get_counters = _lib.jaylink_get_counters
get_counters.argtypes = [_c.POINTER(device_handle), _c.c_uint32, _c.POINTER(_c.c_uint32)]
get_counters.restype = _c.c_int

get_hardware_version = _lib.jaylink_get_hardware_version
get_hardware_version.argtypes = [_c.POINTER(device_handle), _c.POINTER(hardware_version)]
get_hardware_version.restype = _c.c_int

get_hardware_status = _lib.jaylink_get_hardware_status
get_hardware_status.argtypes = [_c.POINTER(device_handle), _c.POINTER(hardware_status)]
get_hardware_status.restype = _c.c_int

get_caps = _lib.jaylink_get_caps
get_caps.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8)]
get_caps.restype = _c.c_int

get_extended_caps = _lib.jaylink_get_extended_caps
get_extended_caps.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8)]
get_extended_caps.restype = _c.c_int

get_free_memory = _lib.jaylink_get_free_memory
get_free_memory.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint32)]
get_free_memory.restype = _c.c_int

read_raw_config = _lib.jaylink_read_raw_config
read_raw_config.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8)]
read_raw_config.restype = _c.c_int

write_raw_config = _lib.jaylink_write_raw_config
write_raw_config.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8)]
write_raw_config.restype = _c.c_int

register = _lib.jaylink_register
register.argtypes = [_c.POINTER(device_handle), _c.POINTER(connection), _c.POINTER(connection), _c.POINTER(_c.c_size_t)]
register.restype = _c.c_int

unregister = _lib.jaylink_unregister
unregister.argtypes = [_c.POINTER(device_handle), _c.POINTER(connection), _c.POINTER(connection), _c.POINTER(_c.c_size_t)]
unregister.restype = _c.c_int

discovery_scan = _lib.jaylink_discovery_scan
discovery_scan.argtypes = [_c.POINTER(context), _c.c_uint32]
discovery_scan.restype = _c.c_int

emucom_read = _lib.jaylink_emucom_read
emucom_read.argtypes = [_c.POINTER(device_handle), _c.c_uint32, _c.c_char_p, _c.POINTER(_c.c_uint32)]
emucom_read.restype = _c.c_int

emucom_write = _lib.jaylink_emucom_write
emucom_write.argtypes = [_c.POINTER(device_handle), _c.c_uint32, _c.c_char_p, _c.POINTER(_c.c_uint32)]
emucom_write.restype = _c.c_int

strerror = _lib.jaylink_strerror
strerror.argtypes = [_c.c_int]
strerror.restype = _c.c_char_p

strerror_name = _lib.jaylink_strerror_name
strerror_name.argtypes = [_c.c_int]
strerror_name.restype = _c.c_char_p

file_read = _lib.jaylink_file_read
file_read.argtypes = [_c.POINTER(device_handle), _c.c_char_p, _c.POINTER(_c.c_uint8), _c.c_uint32, _c.POINTER(_c.c_uint32)]
file_read.restype = _c.c_int

file_write = _lib.jaylink_file_write
file_write.argtypes = [_c.POINTER(device_handle), _c.c_char_p, _c.POINTER(_c.c_uint8), _c.c_uint32, _c.POINTER(_c.c_uint32)]
file_write.restype = _c.c_int

file_get_size = _lib.jaylink_file_get_size
file_get_size.argtypes = [_c.POINTER(device_handle), _c.c_char_p, _c.POINTER(_c.c_uint32)]
file_get_size.restype = _c.c_int

file_delete = _lib.jaylink_file_delete
file_delete.argtypes = [_c.POINTER(device_handle), _c.c_char_p]
file_delete.restype = _c.c_int

jtag_io = _lib.jaylink_jtag_io
jtag_io.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8), _c.POINTER(_c.c_uint8), _c.POINTER(_c.c_uint8), _c.c_uint16, jtag_version]
jtag_io.restype = _c.c_int

jtag_clear_trst = _lib.jaylink_jtag_clear_trst
jtag_clear_trst.argtypes = [_c.POINTER(device_handle)]
jtag_clear_trst.restype = _c.c_int

jtag_set_trst = _lib.jaylink_jtag_set_trst
jtag_set_trst.argtypes = [_c.POINTER(device_handle)]
jtag_set_trst.restype = _c.c_int

log_set_level = _lib.jaylink_log_set_level
log_set_level.argtypes = [_c.POINTER(context), log_level]
log_set_level.restype = _c.c_int

log_get_level = _lib.jaylink_log_get_level
log_get_level.argtypes = [_c.POINTER(context), _c.POINTER(log_level)]
log_get_level.restype = _c.c_int

log_set_callback = _lib.jaylink_log_set_callback
log_set_callback.argtypes = [_c.POINTER(context), log_callback, _c.py_object]
log_set_callback.restype = _c.c_int

log_set_domain = _lib.jaylink_log_set_domain
log_set_domain.argtypes = [_c.POINTER(context), _c.c_char_p]
log_set_domain.restype = _c.c_int

log_get_domain = _lib.jaylink_log_get_domain
log_get_domain.argtypes = [_c.POINTER(context)]
log_get_domain.restype = _c.c_char_p

parse_serial_number = _lib.jaylink_parse_serial_number
parse_serial_number.argtypes = [_c.c_char_p, _c.POINTER(_c.c_int32)]
parse_serial_number.restype = _c.c_int

swd_io = _lib.jaylink_swd_io
swd_io.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8), _c.POINTER(_c.c_uint8), _c.POINTER(_c.c_uint8), _c.c_uint16]
swd_io.restype = _c.c_int

swo_start = _lib.jaylink_swo_start
swo_start.argtypes = [_c.POINTER(device_handle), swo_mode, _c.c_uint32, _c.c_uint32]
swo_start.restype = _c.c_int

swo_stop = _lib.jaylink_swo_stop
swo_stop.argtypes = [_c.POINTER(device_handle)]
swo_stop.restype = _c.c_int

swo_read = _lib.jaylink_swo_read
swo_read.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint8), _c.POINTER(_c.c_uint32)]
swo_read.restype = _c.c_int

swo_get_speeds = _lib.jaylink_swo_get_speeds
swo_get_speeds.argtypes = [_c.POINTER(device_handle), swo_mode, _c.POINTER(swo_speed)]
swo_get_speeds.restype = _c.c_int

set_speed = _lib.jaylink_set_speed
set_speed.argtypes = [_c.POINTER(device_handle), _c.c_uint16]
set_speed.restype = _c.c_int

get_speeds = _lib.jaylink_get_speeds
get_speeds.argtypes = [_c.POINTER(device_handle), _c.POINTER(speed)]
get_speeds.restype = _c.c_int

select_interface = _lib.jaylink_select_interface
select_interface.argtypes = [_c.POINTER(device_handle), target_interface, _c.POINTER(target_interface)]
select_interface.restype = _c.c_int

get_available_interfaces = _lib.jaylink_get_available_interfaces
get_available_interfaces.argtypes = [_c.POINTER(device_handle), _c.POINTER(_c.c_uint32)]
get_available_interfaces.restype = _c.c_int

get_selected_interface = _lib.jaylink_get_selected_interface
get_selected_interface.argtypes = [_c.POINTER(device_handle), _c.POINTER(target_interface)]
get_selected_interface.restype = _c.c_int

clear_reset = _lib.jaylink_clear_reset
clear_reset.argtypes = [_c.POINTER(device_handle)]
clear_reset.restype = _c.c_int

set_reset = _lib.jaylink_set_reset
set_reset.argtypes = [_c.POINTER(device_handle)]
set_reset.restype = _c.c_int

set_target_power = _lib.jaylink_set_target_power
set_target_power.argtypes = [_c.POINTER(device_handle), _c.c_bool]
set_target_power.restype = _c.c_int

has_cap = _lib.jaylink_has_cap
has_cap.argtypes = [_c.POINTER(_c.c_uint8), _c.c_uint32]
has_cap.restype = _c.c_bool

version_package_get_major = _lib.jaylink_version_package_get_major
version_package_get_major.argtypes = []
version_package_get_major.restype = _c.c_int

version_package_get_minor = _lib.jaylink_version_package_get_minor
version_package_get_minor.argtypes = []
version_package_get_minor.restype = _c.c_int

version_package_get_micro = _lib.jaylink_version_package_get_micro
version_package_get_micro.argtypes = []
version_package_get_micro.restype = _c.c_int

version_package_get_string = _lib.jaylink_version_package_get_string
version_package_get_string.argtypes = []
version_package_get_string.restype = _c.c_char_p

version_library_get_current = _lib.jaylink_version_library_get_current
version_library_get_current.argtypes = []
version_library_get_current.restype = _c.c_int

version_library_get_revision = _lib.jaylink_version_library_get_revision
version_library_get_revision.argtypes = []
version_library_get_revision.restype = _c.c_int

version_library_get_age = _lib.jaylink_version_library_get_age
version_library_get_age.argtypes = []
version_library_get_age.restype = _c.c_int

version_library_get_string = _lib.jaylink_version_library_get_string
version_library_get_string.argtypes = []
version_library_get_string.restype = _c.c_char_p

LOG_DOMAIN_DEFAULT = 'jaylink: '
LOG_DOMAIN_MAX_LENGTH = 32
SPEED_ADAPTIVE_CLOCKING = 65535
DEV_CONFIG_SIZE = 256
DEV_CAPS_SIZE = 4
DEV_EXT_CAPS_SIZE = 32
MAX_CONNECTIONS = 16
FILE_NAME_MAX_LENGTH = 255
FILE_MAX_TRANSFER_SIZE = 1048576
EMUCOM_CHANNEL_TIME = 0
EMUCOM_CHANNEL_USER = 65536
