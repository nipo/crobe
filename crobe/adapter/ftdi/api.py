import ctypes as _c
from ...util.dynamic_library import load as _load

_lib = _load("ftdi1", 2)
_libusb = _load("usb-1.0", 0)

enum_chip_type = _c.c_int
CHIP_TYPE = {
    "AM": 0,
    "BM": 1,
    "2232C": 2,
    "R": 3,
    "2232H": 4,
    "4232H": 5,
    "232H": 6,
    "230X": 7,
    }
CHIP_TYPE_NAME = dict([(v, k) for (k, v) in CHIP_TYPE.items()])

enum_parity_type = _c.c_int
PARITY = dict(
    NONE = 0,
    ODD = 1,
    EVEN = 2,
    MARK = 3,
    SPACE = 4,
    )
PARITY_NAME = dict([(v, k) for (k, v) in PARITY.items()])

enum_stopbits_type = _c.c_int
STOP_BIT_1 = 0
STOP_BIT_15 = 1
STOP_BIT_2 = 2

enum_bits_type = _c.c_int
enum_break_type = _c.c_int

enum_bitmode = _c.c_int
BITMODE = dict(
    RESET = 0,
    BITBANG = 1,
    MPSSE = 2,
    SYNCBB = 4,
    MCU = 8,
    OPTO = 16,
    CBUS = 32,
    SYNCFF = 64,
    FT1284 = 128,
    )
BITMODE_NAME = dict([(v, k) for (k, v) in BITMODE.items()])

enum_interface = _c.c_int
INTERFACE = dict(
    ANY = 0,
    A = 1,
    B = 2,
    C = 3,
    D = 4,
    )
INTERFACE_NAME = dict([(v, k) for (k, v) in INTERFACE.items()])

enum_module_detach_mode = _c.c_int
MODULE_DETACH_MODE = dict(
    AUTO = 0,
    DONT = 1,
)

enum_eeprom_value = _c.c_int
EEPROM_VALUE = dict(
    VENDOR_ID = 0,
    PRODUCT_ID = 1,
    SELF_POWERED = 2,
    REMOTE_WAKEUP = 3,
    IS_NOT_PNP = 4,
    SUSPEND_DBUS7 = 5,
    IN_IS_ISOCHRONOUS = 6,
    OUT_IS_ISOCHRONOUS = 7,
    SUSPEND_PULL_DOWNS = 8,
    USE_SERIAL = 9,
    USB_VERSION = 10,
    USE_USB_VERSION = 11,
    MAX_POWER = 12,
    CHANNEL_A_TYPE = 13,
    CHANNEL_B_TYPE = 14,
    CHANNEL_A_DRIVER = 15,
    CHANNEL_B_DRIVER = 16,
    CBUS_FUNCTION_0 = 17,
    CBUS_FUNCTION_1 = 18,
    CBUS_FUNCTION_2 = 19,
    CBUS_FUNCTION_3 = 20,
    CBUS_FUNCTION_4 = 21,
    CBUS_FUNCTION_5 = 22,
    CBUS_FUNCTION_6 = 23,
    CBUS_FUNCTION_7 = 24,
    CBUS_FUNCTION_8 = 25,
    CBUS_FUNCTION_9 = 26,
    HIGH_CURRENT = 27,
    HIGH_CURRENT_A = 28,
    HIGH_CURRENT_B = 29,
    INVERT = 30,
    GROUP0_DRIVE = 31,
    GROUP0_SCHMITT = 32,
    GROUP0_SLEW = 33,
    GROUP1_DRIVE = 34,
    GROUP1_SCHMITT = 35,
    GROUP1_SLEW = 36,
    GROUP2_DRIVE = 37,
    GROUP2_SCHMITT = 38,
    GROUP2_SLEW = 39,
    GROUP3_DRIVE = 40,
    GROUP3_SCHMITT = 41,
    GROUP3_SLEW = 42,
    CHIP_SIZE = 43,
    CHIP_TYPE = 44,
    POWER_SAVE = 45,
    CLOCK_POLARITY = 46,
    DATA_ORDER = 47,
    FLOW_CONTROL = 48,
    CHANNEL_C_DRIVER = 49,
    CHANNEL_D_DRIVER = 50,
    CHANNEL_A_RS485 = 51,
    CHANNEL_B_RS485 = 52,
    CHANNEL_C_RS485 = 53,
    CHANNEL_D_RS485 = 54,
    RELEASE_NUMBER = 55,
    EXTERNAL_OSCILLATOR = 56,
    USER_DATA_ADDR = 57,
    )
EEPROM_VALUE_NAME = dict([(v, k) for (k, v) in EEPROM_VALUE.items()])

CHANNEL_TYPE = dict(
    UART = 0,
    FIFO = 1,
    OPTO = 2,
    CPU = 4,
    FT1284 = 8,
    RS485 = 16,
)
CHANNEL_TYPE_NAME = dict([(v, k) for (k, v) in CHANNEL_TYPE.items()])

DRIVER = dict(
    VCP = 8,
    VCPH = 16,
)
DRIVER_NAME = dict([(v, k) for (k, v) in DRIVER.items()])

DRIVE = {
    '4mA': 0,
    '8mA': 1,
    '12mA': 2,
    '16mA': 3,
}
DRIVE_NAME = dict([(v, k) for (k, v) in DRIVE.items()])

enum_cbus_func = _c.c_int
CBUS = dict(
    TXDEN = 0,
    PWREN = 1,
    RXLED = 2,
    TXLED = 3,
    TXRXLED = 4,
    SLEEP = 5,
    CLK48 = 6,
    CLK24 = 7,
    CLK12 = 8,
    CLK6 = 9,
    IOMODE = 10,
    BB_WR = 11,
    BB_RD = 12,
)
CBUS_NAME = dict([(v, k) for (k, v) in CBUS.items()])

enum_cbush_func = _c.c_int
CBUSH = dict(
    TRISTATE = 0,
    TXLED = 1,
    RXLED = 2,
    TXRXLED = 3,
    PWREN = 4,
    SLEEP = 5,
    DRIVE_0 = 6,
    DRIVE1 = 7,
    IOMODE = 8,
    TXDEN = 9,
    CLK30 = 10,
    CLK15 = 11,
    CLK7_5 = 12,
)

enum_cbusx_func = _c.c_int
CBUSX = dict(
    TRISTATE = 0,
    TXLED = 1,
    RXLED = 2,
    TXRXLED = 3,
    PWREN = 4,
    SLEEP = 5,
    DRIVE_0 = 6,
    DRIVE1 = 7,
    IOMODE = 8,
    TXDEN = 9,
    CLK24 = 10,
    CLK12 = 11,
    CLK6 = 12,
    BAT_DETECT = 13,
    BAT_DETECT_NEG = 14,
    I2C_TXE = 15,
    I2C_RXF = 16,
    VBUS_SENSE = 17,
    BB_WR = 18,
    BB_RD = 19,
    TIME_STAMP = 20,
    AWAKE = 21,
)

class struct_timeval(_c.Structure):
    _fields_ = [
        ('tv_sec', _c.c_long),
        ('tv_usec', _c.c_long),
    ]

class context(_c.Structure):
    pass

class libusb_transfer(_c.Structure):
    pass

class transfer_control(_c.Structure):
    _fields_ = [
        ('completed', _c.c_int),
        ('buf', _c.POINTER(_c.c_ubyte)),
        ('size', _c.c_int),
        ('offset', _c.c_int),
        ('ftdi', _c.POINTER(context)),
        ('transfer', _c.POINTER(libusb_transfer)),
    ]

class libusb_context(_c.Structure):
    pass

class libusb_device_handle(_c.Structure):
    pass
    
class eeprom(_c.Structure):
    pass

context._fields_ = [
    ('usb_ctx', _c.POINTER(libusb_context)),
    ('usb_dev', _c.POINTER(libusb_device_handle)),
    ('usb_read_timeout', _c.c_int),
    ('usb_write_timeout', _c.c_int),
    ('type', enum_chip_type),
    ('baudrate', _c.c_int),
    ('bitbang_enabled', _c.c_ubyte),
    ('readbuffer', _c.POINTER(_c.c_ubyte)),
    ('readbuffer_offset', _c.c_uint),
    ('readbuffer_remaining', _c.c_uint),
    ('readbuffer_chunksize', _c.c_uint),
    ('writebuffer_chunksize', _c.c_uint),
    ('max_packet_size', _c.c_uint),
    ('interface', _c.c_int),
    ('index', _c.c_int),
    ('in_ep', _c.c_int),
    ('out_ep', _c.c_int),
    ('bitbang_mode', _c.c_ubyte),
    ('eeprom', _c.POINTER(eeprom)),
    ('error_str', _c.c_char_p),
    ('module_detach_mode', enum_module_detach_mode),
]

class device_list(_c.Structure):
    pass

class libusb_device(_c.Structure):
    pass

device_list._fields_ = [
    ('next', _c.POINTER(device_list)),
    ('dev', _c.POINTER(libusb_device)),
]

class struct_size_and_time(_c.Structure):
    _fields_ = [
        ('totalBytes', _c.c_uint64),
        ('time', struct_timeval),
    ]

class progress_info(_c.Structure):
    _fields_ = [
        ('first', struct_size_and_time),
        ('prev', struct_size_and_time),
        ('current', struct_size_and_time),
        ('totalTime', _c.c_double),
        ('totalRate', _c.c_double),
        ('currentRate', _c.c_double),
    ]

stream_callback_fn = _c.CFUNCTYPE(_c.c_int, _c.POINTER(_c.c_uint8), _c.c_int,
                                  _c.POINTER(progress_info), _c.POINTER(None))

class version_info(_c.Structure):
    _fields_ = [
        ('major', _c.c_int),
        ('minor', _c.c_int),
        ('micro', _c.c_int),
        ('version_str', _c.c_char_p),
        ('snapshot_str', _c.c_char_p),
    ]

libusb_get_bus_number = _libusb.libusb_get_bus_number
libusb_get_bus_number.argtypes = [_c.POINTER(libusb_device)]
libusb_get_bus_number.restype = _c.c_uint8

libusb_get_device_address = _lib.libusb_get_device_address
libusb_get_device_address.argtypes = [_c.POINTER(libusb_device)]
libusb_get_device_address.restype = _c.c_uint8

init = _lib.ftdi_init
init.argtypes = [_c.POINTER(context)]
init.restype = _c.c_int

new = _lib.ftdi_new
new.argtypes = []
new.restype = _c.POINTER(context)

set_interface = _lib.ftdi_set_interface
set_interface.argtypes = [_c.POINTER(context), enum_interface]
set_interface.restype = _c.c_int

deinit = _lib.ftdi_deinit
deinit.argtypes = [_c.POINTER(context)]
deinit.restype = None

free = _lib.ftdi_free
free.argtypes = [_c.POINTER(context)]
free.restype = None

set_usbdev = _lib.ftdi_set_usbdev
set_usbdev.argtypes = [_c.POINTER(context), _c.POINTER(libusb_device_handle)]
set_usbdev.restype = None

get_library_version = _lib.ftdi_get_library_version
get_library_version.argtypes = []
get_library_version.restype = version_info

usb_find_all = _lib.ftdi_usb_find_all
usb_find_all.argtypes = [_c.POINTER(context), _c.POINTER(_c.POINTER(device_list)), _c.c_int, _c.c_int]
usb_find_all.restype = _c.c_int

list_free = _lib.ftdi_list_free
list_free.argtypes = [_c.POINTER(_c.POINTER(device_list))]
list_free.restype = None

list_free2 = _lib.ftdi_list_free2
list_free2.argtypes = [_c.POINTER(device_list)]
list_free2.restype = None

usb_get_strings = _lib.ftdi_usb_get_strings
usb_get_strings.argtypes = [_c.POINTER(context), _c.POINTER(libusb_device), _c.c_char_p, _c.c_int, _c.c_char_p, _c.c_int, _c.c_char_p, _c.c_int]
usb_get_strings.restype = _c.c_int

usb_get_strings2 = _lib.ftdi_usb_get_strings2
usb_get_strings2.argtypes = [_c.POINTER(context), _c.POINTER(libusb_device), _c.c_char_p, _c.c_int, _c.c_char_p, _c.c_int, _c.c_char_p, _c.c_int]
usb_get_strings2.restype = _c.c_int

eeprom_set_strings = _lib.ftdi_eeprom_set_strings
eeprom_set_strings.argtypes = [_c.POINTER(context), _c.c_char_p, _c.c_char_p, _c.c_char_p]
eeprom_set_strings.restype = _c.c_int

usb_open = _lib.ftdi_usb_open
usb_open.argtypes = [_c.POINTER(context), _c.c_int, _c.c_int]
usb_open.restype = _c.c_int

usb_open_desc = _lib.ftdi_usb_open_desc
usb_open_desc.argtypes = [_c.POINTER(context), _c.c_int, _c.c_int, _c.c_char_p, _c.c_char_p]
usb_open_desc.restype = _c.c_int

usb_open_desc_index = _lib.ftdi_usb_open_desc_index
usb_open_desc_index.argtypes = [_c.POINTER(context), _c.c_int, _c.c_int, _c.c_char_p, _c.c_char_p, _c.c_uint]
usb_open_desc_index.restype = _c.c_int

usb_open_dev = _lib.ftdi_usb_open_dev
usb_open_dev.argtypes = [_c.POINTER(context), _c.POINTER(libusb_device)]
usb_open_dev.restype = _c.c_int

usb_open_string = _lib.ftdi_usb_open_string
usb_open_string.argtypes = [_c.POINTER(context), _c.c_char_p]
usb_open_string.restype = _c.c_int

usb_close = _lib.ftdi_usb_close
usb_close.argtypes = [_c.POINTER(context)]
usb_close.restype = _c.c_int

usb_reset = _lib.ftdi_usb_reset
usb_reset.argtypes = [_c.POINTER(context)]
usb_reset.restype = _c.c_int

usb_purge_rx_buffer = _lib.ftdi_usb_purge_rx_buffer
usb_purge_rx_buffer.argtypes = [_c.POINTER(context)]
usb_purge_rx_buffer.restype = _c.c_int

usb_purge_tx_buffer = _lib.ftdi_usb_purge_tx_buffer
usb_purge_tx_buffer.argtypes = [_c.POINTER(context)]
usb_purge_tx_buffer.restype = _c.c_int

usb_purge_buffers = _lib.ftdi_usb_purge_buffers
usb_purge_buffers.argtypes = [_c.POINTER(context)]
usb_purge_buffers.restype = _c.c_int

set_baudrate = _lib.ftdi_set_baudrate
set_baudrate.argtypes = [_c.POINTER(context), _c.c_int]
set_baudrate.restype = _c.c_int

set_line_property = _lib.ftdi_set_line_property
set_line_property.argtypes = [_c.POINTER(context), enum_bits_type, enum_stopbits_type, enum_parity_type]
set_line_property.restype = _c.c_int

set_line_property2 = _lib.ftdi_set_line_property2
set_line_property2.argtypes = [_c.POINTER(context), enum_bits_type, enum_stopbits_type, enum_parity_type, enum_break_type]
set_line_property2.restype = _c.c_int

read_data = _lib.ftdi_read_data
read_data.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
read_data.restype = _c.c_int

read_data_set_chunksize = _lib.ftdi_read_data_set_chunksize
read_data_set_chunksize.argtypes = [_c.POINTER(context), _c.c_uint]
read_data_set_chunksize.restype = _c.c_int

read_data_get_chunksize = _lib.ftdi_read_data_get_chunksize
read_data_get_chunksize.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_uint)]
read_data_get_chunksize.restype = _c.c_int

write_data = _lib.ftdi_write_data
write_data.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
write_data.restype = _c.c_int

write_data_set_chunksize = _lib.ftdi_write_data_set_chunksize
write_data_set_chunksize.argtypes = [_c.POINTER(context), _c.c_uint]
write_data_set_chunksize.restype = _c.c_int

write_data_get_chunksize = _lib.ftdi_write_data_get_chunksize
write_data_get_chunksize.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_uint)]
write_data_get_chunksize.restype = _c.c_int

readstream = _lib.ftdi_readstream
readstream.argtypes = [_c.POINTER(context), _c.POINTER(stream_callback_fn), _c.POINTER(None), _c.c_int, _c.c_int]
readstream.restype = _c.c_int

write_data_submit = _lib.ftdi_write_data_submit
write_data_submit.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
write_data_submit.restype = _c.POINTER(transfer_control)

read_data_submit = _lib.ftdi_read_data_submit
read_data_submit.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
read_data_submit.restype = _c.POINTER(transfer_control)

transfer_data_done = _lib.ftdi_transfer_data_done
transfer_data_done.argtypes = [_c.POINTER(transfer_control)]
transfer_data_done.restype = _c.c_int

transfer_data_cancel = _lib.ftdi_transfer_data_cancel
transfer_data_cancel.argtypes = [_c.POINTER(transfer_control), _c.POINTER(struct_timeval)]
transfer_data_cancel.restype = None

set_bitmode = _lib.ftdi_set_bitmode
set_bitmode.argtypes = [_c.POINTER(context), _c.c_ubyte, _c.c_ubyte]
set_bitmode.restype = _c.c_int

disable_bitbang = _lib.ftdi_disable_bitbang
disable_bitbang.argtypes = [_c.POINTER(context)]
disable_bitbang.restype = _c.c_int

read_pins = _lib.ftdi_read_pins
read_pins.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte)]
read_pins.restype = _c.c_int

set_latency_timer = _lib.ftdi_set_latency_timer
set_latency_timer.argtypes = [_c.POINTER(context), _c.c_ubyte]
set_latency_timer.restype = _c.c_int

get_latency_timer = _lib.ftdi_get_latency_timer
get_latency_timer.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte)]
get_latency_timer.restype = _c.c_int

poll_modem_status = _lib.ftdi_poll_modem_status
poll_modem_status.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ushort)]
poll_modem_status.restype = _c.c_int

setflowctrl = _lib.ftdi_setflowctrl
setflowctrl.argtypes = [_c.POINTER(context), _c.c_int]
setflowctrl.restype = _c.c_int

setdtr_rts = _lib.ftdi_setdtr_rts
setdtr_rts.argtypes = [_c.POINTER(context), _c.c_int, _c.c_int]
setdtr_rts.restype = _c.c_int

setdtr = _lib.ftdi_setdtr
setdtr.argtypes = [_c.POINTER(context), _c.c_int]
setdtr.restype = _c.c_int

setrts = _lib.ftdi_setrts
setrts.argtypes = [_c.POINTER(context), _c.c_int]
setrts.restype = _c.c_int

set_event_char = _lib.ftdi_set_event_char
set_event_char.argtypes = [_c.POINTER(context), _c.c_ubyte, _c.c_ubyte]
set_event_char.restype = _c.c_int

set_error_char = _lib.ftdi_set_error_char
set_error_char.argtypes = [_c.POINTER(context), _c.c_ubyte, _c.c_ubyte]
set_error_char.restype = _c.c_int

eeprom_initdefaults = _lib.ftdi_eeprom_initdefaults
eeprom_initdefaults.argtypes = [_c.POINTER(context), _c.c_char_p, _c.c_char_p, _c.c_char_p]
eeprom_initdefaults.restype = _c.c_int

eeprom_build = _lib.ftdi_eeprom_build
eeprom_build.argtypes = [_c.POINTER(context)]
eeprom_build.restype = _c.c_int

eeprom_decode = _lib.ftdi_eeprom_decode
eeprom_decode.argtypes = [_c.POINTER(context), _c.c_int]
eeprom_decode.restype = _c.c_int

get_eeprom_value = _lib.ftdi_get_eeprom_value
get_eeprom_value.argtypes = [_c.POINTER(context), enum_eeprom_value, _c.POINTER(_c.c_int)]
get_eeprom_value.restype = _c.c_int

set_eeprom_value = _lib.ftdi_set_eeprom_value
set_eeprom_value.argtypes = [_c.POINTER(context), enum_eeprom_value, _c.c_int]
set_eeprom_value.restype = _c.c_int

get_eeprom_buf = _lib.ftdi_get_eeprom_buf
get_eeprom_buf.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
get_eeprom_buf.restype = _c.c_int

set_eeprom_buf = _lib.ftdi_set_eeprom_buf
set_eeprom_buf.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_ubyte), _c.c_int]
set_eeprom_buf.restype = _c.c_int

set_eeprom_user_data = _lib.ftdi_set_eeprom_user_data
set_eeprom_user_data.argtypes = [_c.POINTER(context), _c.c_char_p, _c.c_int]
set_eeprom_user_data.restype = _c.c_int

read_eeprom = _lib.ftdi_read_eeprom
read_eeprom.argtypes = [_c.POINTER(context)]
read_eeprom.restype = _c.c_int

read_chipid = _lib.ftdi_read_chipid
read_chipid.argtypes = [_c.POINTER(context), _c.POINTER(_c.c_uint)]
read_chipid.restype = _c.c_int

write_eeprom = _lib.ftdi_write_eeprom
write_eeprom.argtypes = [_c.POINTER(context)]
write_eeprom.restype = _c.c_int

erase_eeprom = _lib.ftdi_erase_eeprom
erase_eeprom.argtypes = [_c.POINTER(context)]
erase_eeprom.restype = _c.c_int

read_eeprom_location = _lib.ftdi_read_eeprom_location
read_eeprom_location.argtypes = [_c.POINTER(context), _c.c_int, _c.POINTER(_c.c_ushort)]
read_eeprom_location.restype = _c.c_int

write_eeprom_location = _lib.ftdi_write_eeprom_location
write_eeprom_location.argtypes = [_c.POINTER(context), _c.c_int, _c.c_ushort]
write_eeprom_location.restype = _c.c_int

get_error_string = _lib.ftdi_get_error_string
get_error_string.argtypes = [_c.POINTER(context)]
get_error_string.restype = _c.c_char_p

# MPSSE shift command (oring mask)
MPSSE_WRITE_NEG  = 0x01
MPSSE_BITS       = 0x02
MPSSE_READ_NEG   = 0x04
MPSSE_LSB        = 0x08
MPSSE_WRITE      = 0x10
MPSSE_READ       = 0x20
MPSSE_TMS        = 0x40
MPSSE_MANAGEMENT = 0x80

# MPSSE management commands
MPSSE_SET_BITS_LOW         = MPSSE_MANAGEMENT | 0x00
MPSSE_GET_BITS_LOW         = MPSSE_MANAGEMENT | 0x01
MPSSE_SET_BITS_HIGH        = MPSSE_MANAGEMENT | 0x02
MPSSE_GET_BITS_HIGH        = MPSSE_MANAGEMENT | 0x03
MPSSE_LOOPBACK_ENABLE      = MPSSE_MANAGEMENT | 0x04
MPSSE_LOOPBACK_DISABLE     = MPSSE_MANAGEMENT | 0x05
MPSSE_CLK_DIV              = MPSSE_MANAGEMENT | 0x06
MPSSE_SEND_IMMEDIATE       = MPSSE_MANAGEMENT | 0x07
MPSSE_WAIT_ON_HIGH         = MPSSE_MANAGEMENT | 0x08
MPSSE_WAIT_ON_LOW          = MPSSE_MANAGEMENT | 0x09
MPSSE_CLK_DIV5_DISABLE     = MPSSE_MANAGEMENT | 0x0a
MPSSE_CLK_DIV5_ENABLE      = MPSSE_MANAGEMENT | 0x0b
MPSSE_3_PHASE_ENABLE       = MPSSE_MANAGEMENT | 0x0c
MPSSE_3_PHASE_DISABLE      = MPSSE_MANAGEMENT | 0x0d
MPSSE_CLK_BITS             = MPSSE_MANAGEMENT | 0x0e
MPSSE_CLK_BYTES            = MPSSE_MANAGEMENT | 0x0f
MPSSE_READ_SHORT           = MPSSE_MANAGEMENT | 0x10
MPSSE_READ_EXTENDED        = MPSSE_MANAGEMENT | 0x11
MPSSE_WRITE_SHORT          = MPSSE_MANAGEMENT | 0x12
MPSSE_WRITE_EXTENDED       = MPSSE_MANAGEMENT | 0x13
MPSSE_CLK_WAIT_HIGH        = MPSSE_MANAGEMENT | 0x14
MPSSE_CLK_WAIT_LOW         = MPSSE_MANAGEMENT | 0x15
MPSSE_ADAPTIVE_ENABLE      = MPSSE_MANAGEMENT | 0x16
MPSSE_ADAPTIVE_DISABLE     = MPSSE_MANAGEMENT | 0x17
MPSSE_CLK_BYTES_OR_HIGH    = MPSSE_MANAGEMENT | 0x1c
MPSSE_CLK_BYTES_OR_LOW     = MPSSE_MANAGEMENT | 0x1d
MPSSE_DRIVE_OPEN_COLLECTOR = MPSSE_MANAGEMENT | 0x1e

SIO_RESET = 0
SIO_MODEM_CTRL = 1
SIO_SET_FLOW_CTRL = 2
SIO_SET_BAUD_RATE = 3
SIO_SET_DATA = 4
SIO_RESET_REQUEST = SIO_RESET
SIO_SET_BAUDRATE_REQUEST = SIO_SET_BAUD_RATE
SIO_SET_DATA_REQUEST = SIO_SET_DATA
SIO_SET_FLOW_CTRL_REQUEST = SIO_SET_FLOW_CTRL
SIO_SET_MODEM_CTRL_REQUEST = SIO_MODEM_CTRL
SIO_POLL_MODEM_STATUS_REQUEST = 5
SIO_SET_EVENT_CHAR_REQUEST = 6
SIO_SET_ERROR_CHAR_REQUEST = 7
SIO_SET_LATENCY_TIMER_REQUEST = 9
SIO_GET_LATENCY_TIMER_REQUEST = 10
SIO_SET_BITMODE_REQUEST = 11
SIO_READ_PINS_REQUEST = 12
SIO_READ_EEPROM_REQUEST = 144
SIO_WRITE_EEPROM_REQUEST = 145
SIO_ERASE_EEPROM_REQUEST = 146

SIO_RESET_SIO = 0
SIO_RESET_PURGE_RX = 1
SIO_RESET_PURGE_TX = 2
SIO_DISABLE_FLOW_CTRL = 0
SIO_RTS_CTS_HS = (1 << 8)
SIO_DTR_DSR_HS = (2 << 8)
SIO_XON_XOFF_HS = (4 << 8)
SIO_SET_DTR_MASK = 1
SIO_SET_DTR_HIGH = (1 | (SIO_SET_DTR_MASK << 8))
SIO_SET_DTR_LOW = (0 | (SIO_SET_DTR_MASK << 8))
SIO_SET_RTS_MASK = 2
SIO_SET_RTS_HIGH = (2 | (SIO_SET_RTS_MASK << 8))
SIO_SET_RTS_LOW = (0 | (SIO_SET_RTS_MASK << 8))
SIO_RTS_CTS_HS = (1 << 8)

FTDI_URB_USERCONTEXT_COOKIE = 1

FT1284_CLK_IDLE_STATE = 1
FT1284_DATA_LSB = 2
FT1284_FLOW_CONTROL = 4

POWER_SAVE_DISABLE_H = 128

USE_SERIAL_NUM = 8

INVERT_TXD = 1
INVERT_RXD = 2
INVERT_RTS = 4
INVERT_CTS = 8
INVERT_DTR = 16
INVERT_DSR = 32
INVERT_DCD = 64
INVERT_RI = 128

SLOW_SLEW = 4
IS_SCHMITT = 8

USE_USB_VERSION_BIT = 16

SUSPEND_DBUS7_BIT = 128

HIGH_CURRENT_DRIVE = 16
HIGH_CURRENT_DRIVE_R = 4

def DIV_VALUE(rate):
    if rate > 6000000:
        return 0
    return min((int(6000000 / rate - 1), 65535))
