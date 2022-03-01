from . import model
from ..protocol import jtag, swd, base
from ..bitstring import *
import usb.util
import enum
import math

__all__ = []

class XdsOp(enum.IntEnum):
    JtagConnect     = 0x01
    JtagDisconnect  = 0x02
    VersionGet      = 0x03
    ClockDelaySet   = 0x04
    JtagTrstSet     = 0x05
    JtagTckCycle    = 0x07
    JtagGotoState   = 0x09
    JtagScan        = 0x0c
    SrstSet         = 0x0e
    CmapiConnect    = 0x0f
    CmapiDisconnect = 0x10
    CmapiAcquire    = 0x11
    CmapiRelease    = 0x12
    CmapiRegRead    = 0x15
    CmapiRegWrite   = 0x16
    JtagToSwd       = 0x17
    SwdToJtag       = 0x18
    JtagToCjtag     = 0x2b
    CjtagToJtag     = 0x2c
    SupplySet       = 0x32
    DapRequest      = 0x3a
    JtagScanRequest = 0x3b
    JtagPathmove    = 0x3c

class XdsErrorLevel(enum.IntEnum):
    BadCommand  = -120
    Fail        = -261
    SwdWait     = -613
    SwdFault    = -614
    SwdProtocol = -615
    SwdParity   = -616
    SwdDeviceId = -617

class XdsJtagTransit(enum.IntEnum):
    Shortest = 1
    ThroughCapture = 2
    ThroughRun = 3

class XdsJtagState(enum.IntEnum):
    Reset     = 1
    Run       = 2
    ShiftDr   = 3
    ShiftIr   = 4
    PauseDr   = 5
    PauseIr   = 6
    Exit1Dr   = 8
    Exit1Ir   = 9
    Exit2Dr   = 10
    Exit2Ir   = 11
    SelectDr  = 12
    SelectIr  = 13
    UpdateDr  = 14
    UpdateIr  = 15
    CaptureDr = 16
    CaptureIr = 17

class XdsCmapiType(enum.IntEnum):
    Ap = 0
    Dp = 1
    
class XdsError(Exception):
    def __init__(self, level):
        try:
            err = XdsErrorLevel(level)
            super().__init__("XDS Error", err)
        except:
            super().__init__("XDS Error", level)

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x0451, idProduct = 0xbef3))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x0451, idProduct = 0xbef4))
class Adapter(model.Adapter):
    supported_interfaces = ["jtag", "swd"]

    def ctrl_out(self, op, value, index, data = b''):
        self.logger.protocol("CTRL OUT %02x v %04x i %04x %s",
                             op, value, index,
                             data.hex())

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
        data = bytes(data)
        self.logger.protocol("-> %s", data.hex())
        return data

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "xds110-%s" % (serial,))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.handle = device

    def open(self, interface_name):
        if interface_name.lower() == "jtag":
            return JtagInterface(self)
        if interface_name.lower() == "swd":
            return SwdInterface(self)

class Handle:
    FW_OCD_MIN = 0x02030011
    FW_FAST_TCK = 0x03000000
    FW_FASTER_TCK = 0x03000003
    HW_STANDALONE = 0x21

    def __init__(self, adapter):
        self.__rate = self.xds_divisor_calc(1e6)
        self.__rate_dirty = True
        self.__voltage = None
        self.__voltage_dirty = True

        self.handle = adapter.handle

        cfg = self.handle.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.handle.set_configuration(1)
            cfg = self.handle.get_active_configuration()

        self.intf = None
        for intf in cfg:
            if intf.bInterfaceClass == 0xff and \
               intf.bInterfaceSubClass == 0 and \
               intf.bInterfaceProtocol == 0:
                self.intf = intf
                break
        if self.intf is None:
            raise RuntimeError("No relevant interface found")
        usb.util.claim_interface(self.handle, self.intf)
        
        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)

        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)
        
    def start(self):
        self.logger.note("Using interface %d, EP_IN: %02x, EP_OUT: %02x",
                         self.intf.index, self.ep_in.bEndpointAddress, self.ep_out.bEndpointAddress)
        fw, hw = self.xds_version_get()
        self.fw_version = fw
        self.hw_version = hw
        self.logger.note("Firmware version %08x, Hardware version %04x", fw, hw)
        self.can_do_ocd = self.fw_version >= self.FW_OCD_MIN
        self.has_supply = self.hw_version == self.HW_STANDALONE
        self.max_freq = 2.5e6
        if fw >= self.FW_FAST_TCK:
            self.max_freq = 8.5e6
        if fw >= self.FW_FASTER_TCK:
            self.max_freq = 12e6

    def _voltage_set(self, voltage):
        self.__voltage = voltage
        self.__voltage_dirty = True

    def freq_update(self, freq):
        divisor, freq = self.xds_divisor_calc(freq)
        if self.__rate == (divisor, freq):
            return freq
        self.__rate = divisor, freq
        self.__rate_dirty = True
        return freq

    # Default, overriden at open
    max_freq = 2.5e6
    FREQ_MAP = [
        (14e6, 0),
        (10e6, -3),
        (12e6, -2),
        (8.5e6, 1),
        (5.5e6, 2),
        (0, None),
    ]
    
    def xds_divisor_calc(self, freq):
        if freq is None:
            freq = 14e6
        freq = min(freq, self.max_freq)
        for fmin, divisor in self.FREQ_MAP:
            if freq > fmin and fmin:
                freq = fmin
                break
        if divisor is None:
            divisor = min(65534, max(int(math.ceil(17.1e6 / freq - 1)), 1))
            freq = 17.1e6 / (divisor + 1)
        return divisor, freq

    def target_setup(self):
        if self.__voltage_dirty:
            if not self.has_supply:
                if self.__voltage:
                    self.logger.error("This probe does not support supplying voltage")
            else:
                self.xds_supply_set(self.__voltage)
            self.__voltage_dirty = False

        if self.__rate_dirty:
            div, freq = self.__rate
            self.logger.protocol("Rate is dirty, setting clock to %s, div=%d", freq, div)
            self.xds_clock_rate_set(div)
            self.__rate_dirty = False
            
    def __packet_out(self, data, timeout = None):
        data = b'*' + len(data).to_bytes(2, "little") + data
        self.logger.protocol("Packet OUT %s", data.hex())
        self.handle.write(self.ep_out.bEndpointAddress, data, int((timeout or 1.) * 1000))

    def __packet_in(self, timeout = None):
        self.logger.protocol("Packet IN")
        data = self.handle.read(self.ep_in.bEndpointAddress, self.ep_in.wMaxPacketSize, int((timeout or 1.) * 1000))
        data = bytes(data)
        self.logger.protocol("-> %s", data.hex())
        if data[0:1] != b'*':
            return
        size = int.from_bytes(data[1:3], "little")
        data = data[3:]
        while len(data) < size:
            chunk = self.handle.read(self.ep_in.bEndpointAddress, self.ep_in.wMaxPacketSize, int((timeout or 1.) * 1000))
            data += chunk
        return data[:size]

    def __command(self, operation, args = b'', raw = False):
        blob = bytes([int(operation)]) + args
        self.__packet_out(blob)
        rsp = self.__packet_in()
        if raw:
            return rsp
        error = int.from_bytes(rsp[:4], "little", signed = True)
        data = rsp[4:]
        if error:
            raise XdsError(error)
        return data

    # Command wrappers
    def xds_version_get(self):
        rsp = self.__command(XdsOp.VersionGet)
        fw_id = int.from_bytes(rsp[:4], "little")
        hw_id = int.from_bytes(rsp[4:8], "little")
        return fw_id, hw_id

    def xds_clock_rate_set(self, divisor):
        self.__command(XdsOp.ClockDelaySet, int(divisor).to_bytes(4, "little"))

    def xds_jtag_goto_state(self, st, transit = XdsJtagTransit.Shortest):
        self.__command(XdsOp.JtagGotoState, int(st).to_bytes(4, "little") + int(transit).to_bytes(4, "little"))

    def xds_jtag_tck_cycles(self, count):
        self.__command(XdsOp.JtagTckCycle, int(count).to_bytes(4, "little"))

    def xds_srst_set(self, asserted):
        self.__command(XdsOp.SrstSet, bytes([asserted]))

    def xds_jtag_connect(self):
        self.__command(XdsOp.JtagConnect)

    def xds_jtag_to_swd(self):
        self.__command(XdsOp.JtagToSwd)

    def xds_swd_to_jtag(self):
        self.__command(XdsOp.SwdToJtag)

    def xds_supply_set(self, voltage = None):
        if voltage is not None and not (1.8 <= voltage <= 3.6):
            raise ValueError(f"Bad voltage {voltage} V")
        self.__command(XdsOp.SupplySet,
                       int((voltage or 0) * 1000).to_bytes(4, "little")
                       + int(voltage is not None).to_bytes(4, "little"))

    def xds_jtag_scan(self, is_dr, tdi, read_tdo = True):
        bit_count = len(tdi)
        out_byte_count = (bit_count + 7) // 8
        in_byte_count = out_byte_count if read_tdo else 0
        shift_state = XdsJtagState.ShiftDr if is_dr else XdsJtagState.ShiftIr
        end_state = XdsJtagState.PauseDr if is_dr else XdsJtagState.PauseIr
        assert len(tdi) / 8 < 4096 - 19
        cmd = [bit_count & 0xff, bit_count >> 8,
               int(shift_state), int(XdsJtagTransit.Shortest),
               int(end_state), int(XdsJtagTransit.Shortest),
               0, 0, # Pre
               0, 0, # Post
               0, 0, # Extra after
               1, 0, # Rep count
               out_byte_count & 0xff, out_byte_count >> 8,
               in_byte_count & 0xff, in_byte_count >> 8,
               
        ]
        if read_tdo:
            tdo = self.__command(XdsOp.JtagScan, bytes(cmd) + bytes(tdi))
            return BitString(tdo, len(tdi))

    def cmapi_reg_read(self, type, ap, addr):
        r = self.__command(XdsOp.CmapiRegRead, bytes([int(type), int(ap), int(addr)]))
        assert len(r) == 4
        return int.from_bytes(r, "little")

    def cmapi_reg_write(self, type, ap, addr, data):
        self.__command(XdsOp.CmapiRegWrite, bytes([int(type), int(ap), int(addr)]) + int(data).to_bytes(4, "little"))

    def cmapi_acquire(self):
        self.__command(XdsOp.CmapiAcquire)

    def cmapi_release(self):
        self.__command(XdsOp.CmapiRelease)

    def cmapi_disconnect(self):
        self.__command(XdsOp.CmapiDisconnect)

    def cmapi_connect(self):
        r = self.__command(XdsOp.CmapiConnect)
        assert len(r) == 4
        return int.from_bytes(r, "little")

        assert len(r) == 8
        error = int.from_bytes(r[0:4], "little")
        idcode = int.from_bytes(r[4:8], "little")
        if idcode != 0 and idcode != 0xfffffff:
            return idcode
        raise XdsError(error)

    def xds_jtag_to_swd(self):
        self.__command(XdsOp.JtagToSwd)
        
class JtagInterface(jtag.Interface, Handle):
    def __init__(self, adapter):
        Handle.__init__(self, adapter)
        jtag.Interface.__init__(self, adapter, "jtag")

    def start(self):
        Handle.start(self)
        self.xds_jtag_connect()
        self.__is_dr = None
        jtag.Interface.start(self)

    def freq_update(self, freq):
        return Handle.freq_update(self, freq)
        
    def option_set(self, opt):
        if opt.startswith("vsupply="):
            self._voltage_set(float(opt[8:]))
            return

        return jtag.Interface.option_set(opt)

    def _execute(self, operation_list):

        self.logger.protocol("Running %s", operation_list)

        self.target_setup()

        for op in operation_list:
            if isinstance(op, jtag.CaptureDr):
                self.xds_jtag_goto_state(XdsJtagState.PauseDr,
                                         XdsJtagTransit.ThroughCapture if self.__is_dr == True else XdsJtagTransit.Shortest)
                self.__is_dr = True

            elif isinstance(op, jtag.CaptureIr):
                self.xds_jtag_goto_state(XdsJtagState.PauseIr,
                                         XdsJtagTransit.ThroughCapture if self.__is_dr == False else XdsJtagTransit.Shortest)
                self.__is_dr = False

            elif isinstance(op, jtag.Reset):
                self.xds_jtag_goto_state(XdsJtagState.Reset)
                self.xds_jtag_tck_cycles(len(op.tms))

            elif isinstance(op, base.Reset):
                self.xds_srst_set(op.asserted)

            elif isinstance(op, jtag.Run):
                self.xds_jtag_goto_state(XdsJtagState.Run)
                self.xds_jtag_tck_cycles(op.cycles)

            elif isinstance(op, jtag.SwdToJtag):
                self.xds_swd_to_jtag()

            elif isinstance(op, jtag.Shift):
                if isinstance(op.tdi, int):
                    tdi = BitString(0, op.tdi)
                else:
                    tdi = op.tdi
                assert isinstance(tdi, BitStringBase)

                if op.read_tdo:
                    op.tdo = BitString(0,0)
                max_bit_count = (4096 - 19) * 8
                for off in range(0, len(tdi), max_bit_count):
                    chunk = tdi[off : off + max_bit_count]

                    tdo = self.xds_jtag_scan(self.__is_dr, chunk, op.read_tdo)
                    if op.read_tdo:
                        op.tdo += tdo
            else:
                raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

class SwdInterface(swd.Interface, Handle):
    turnaround_supported = False

    def __init__(self, adapter):
        Handle.__init__(self, adapter)
        swd.Interface.__init__(self, adapter, "swd")
        self.__bank = 0
        self.__ap = 0
        self.__rdbuf = None

    def start(self):
        pass
        #Handle.start(self)
        #self.xds_swd_to_jtag()
        #self.cmapi_acquire()
        #swd.Interface.start(self)
    
    def freq_update(self, freq):
        return Handle.freq_update(self, freq)
        
    def option_set(self, opt):
        if opt.startswith("vsupply="):
            self._voltage_set(float(opt[8:]))
            return

        return swd.Interface.option_set(opt)

    @property
    def turnaround_cycles(self):
        return 1

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        pass

    def _execute(self, operation_list):
        self.logger.protocol("Running %s", operation_list)

        self.target_setup()

        for op in operation_list:
            if isinstance(op, swd.Read):
                try:
                    if not op.ap and op.addr == 0:
                        v = self.cmapi_connect()
                        op.data = v
                        op.ack = swd.Ack.OK
                    elif not op.ap and op.addr == 3:
                        op.data = self.__rdbuf
                        self.__rdbuf = None
                        op.ack = swd.Ack.OK
                    else:
                        v = self.cmapi_reg_read(
                            XdsCmapiType.Ap if op.ap else XdsCmapiType.Dp,
                            self.__ap, ((op.addr & 3) << 2) | (self.__bank << 4))
                        op.data = v
                        op.ack = swd.Ack.OK
                        if op.ap:
                            self.__rdbuf, op.data = op.data, self.__rdbuf
                except XdsError as e:
                    rv = e.args[1]
                    if rv == XdsErrorLevel.SwdWait:
                        op.ack = swd.Ack.WAIT
                    elif rv == XdsErrorLevel.SwdFault:
                        op.ack = swd.Ack.ERROR
                    elif rv == XdsErrorLevel.SwdParity:
                        op.ack = swd.Ack.PARITY_ERR
                    elif rv == XdsErrorLevel.SwdDeviceId:
                        op.ack = swd.Ack.LOW
                    else:
                        raise

            elif isinstance(op, swd.Write):
                if (not op.ap) and op.addr == 2:
                    self.__bank = (op.data >> 4) & 0xf
                    self.__ap = (op.data >> 24) & 0xff

                self.cmapi_reg_write(
                    XdsCmapiType.Ap if op.ap else XdsCmapiType.Dp,
                    self.__ap, ((op.addr & 3) << 2) | (self.__bank << 4), op.data)
                op.ack = swd.Ack.OK

            elif isinstance(op, swd.Wakeup):
                #self.xds_jtag_to_swd()
                #self.cmapi_acquire()
                pass

            elif isinstance(op, base.Reset):
                self.xds_srst_set(op.asserted)

            elif isinstance(op, swd.JtagToSwd):
                self.xds_jtag_to_swd()

            elif isinstance(op, swd.Run):
                pass
                #self.xds_jtag_tck_cycles(op.cycles)
                

            else:
                raise base.ProtocolError("Unknown SWD operation %s" % type(op))
