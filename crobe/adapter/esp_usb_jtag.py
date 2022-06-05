from . import model
from ..model import PortComponent
from ..protocol import jtag, base
from .. import bitstring
from ..util.pretty import metric
from collections import deque
import usb.core
import usb.control
import usb.util
import time
import os
import math
import threading
import weakref
import struct
import enum

__all__ = []

class BackgroundWriter(threading.Thread):
    def __init__(self, device, ep, data, timeout):
        threading.Thread.__init__(self)
        self.device = device
        self.ep = ep
        self.data = data
        self.timeout = timeout

    def run(self):
        self.device.write(self.ep.bEndpointAddress, self.data,
                          int(self.timeout * 1000))
        
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x303a, idProduct = 0x1001))
class Adapter(model.Adapter):
    supported_interfaces = ["jtag"]

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber).replace(":", "")
        return cls(d, "esp-%s" % (serial))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)
        self.device = device
        self.jtag_interface = None

    def jtag_descriptor_get(self):
        # Doc says 256 bytes, implementation on openocd-esp32 does 255.
        # Device crashes with 256...
        info = self.device.ctrl_transfer(bmRequestType = 0x80,
                                         bRequest = 0x06,
                                         wValue = 0x2000,
                                         wIndex = 0,
                                         data_or_wLength = 255)
        return bytes(info)

    def divisor_set(self, interface, value):
        self.device.ctrl_transfer(bmRequestType = 0x40,
                                  bRequest = 0x00,
                                  wValue = int(value),
                                  wIndex = interface,
                                  data_or_wLength = b'')

    def io_set(self, interface, iobits):
        self.device.ctrl_transfer(bmRequestType = 0x40,
                                  bRequest = 0x01,
                                  wValue = int(iobits),
                                  wIndex = interface,
                                  data_or_wLength = b'')
        
    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            return None

        if self.jtag_interface is None:
            configuration = None
            interface = None
            
            for cidx, config in enumerate(self.device):
                for iidx, intf in enumerate(config):
                    if intf.bInterfaceClass != 0xff:
                        continue
                    if intf.bInterfaceSubClass != 0xff:
                        continue
                    if intf.bInterfaceProtocol != 0x01:
                        continue

                    configuration = config
                    interface = intf

            if not interface:
                raise RuntimeError("JTAG interface not found")

            if self.device.is_kernel_driver_active(intf.bInterfaceNumber):
                self.device.detach_kernel_driver(intf.bInterfaceNumber)

            if self.device.get_active_configuration() != configuration.bConfigurationValue:
                try:
                    self.device.set_configuration(configuration.bConfigurationValue)
                    time.sleep(.5)
                except usb.core.USBError:
                    pass

            usb.util.claim_interface(self.device, interface)

            info = self.jtag_descriptor_get()
            self.logger.info("Info blob: %s", info)
            ver, total_len = info[:2]
            assert total_len == len(info)
            assert ver == 1
            point = 2
            speed, div_min, div_max = 80e6, 1, 255
            while point < len(info):
                t, l = info[point:point+2]
                if t == 1:
                    # JTAG
                    assert l >= 8
                    speed, div_min, div_max = struct.unpack("<HHH", info[point+2:point+8])
                    speed *= 10e3
                    self.logger.note("JTAG caps descriptor, base freq: %s, div %d-%d",
                                     metric(speed, "Hz"), div_min, div_max)
                point += l

            self.base_freq = speed
            self.div_min = div_min
            self.div_max = div_max
                
            self.jtag_ep_in = usb.util.find_descriptor(
                interface,
                custom_match = lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) ==
                usb.util.ENDPOINT_IN)
            self.jtag_ep_out = usb.util.find_descriptor(
                interface,
                custom_match = lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) ==
                usb.util.ENDPOINT_OUT)
            self.jtag_interface = interface
        
        if interface_name.lower() == "jtag":
            return JtagInterface(self)

    def jtag_execute(self, operations, timeout):
        #self.logger.protocol("Running JTAG %s", operations)

        pending = []
        rx_bit_size = 0
        b = 0
        b_ready = False
        for o in operations:
            nibbles, rxs = o.to_nibbles()
            for n in nibbles:
                b <<= 4
                b |= n
                if b_ready:
                    pending.append(b)
                    b = 0
                b_ready = not b_ready
            rx_bit_size += rxs

        if b_ready:
            pending.append((b << 4) | self.JTAG_CMD_FLUSH)
        else:
            pending.append((self.JTAG_CMD_FLUSH << 4) | self.JTAG_CMD_FLUSH)
            
        rx_data = self.jtag_io(bytes(pending), (rx_bit_size + 7) // 8, timeout)

        if rx_bit_size:
            return bitstring.BitString(rx_data, rx_bit_size)
        return bitstring.BitString(0, 0)

    def jtag_io(self, out_data, in_data_size, timeout):
        rx_size = in_data_size
        #if not rx_size:
        #    rx_size = self.jtag_ep_in.wMaxPacketSize
        #rx_size += (-rx_size % self.jtag_ep_in.wMaxPacketSize)

        bw = BackgroundWriter(self.device, self.jtag_ep_out,
                              out_data, timeout)
        bw.start()

        rd = None
        while rd is None or len(rd) < rx_size:
            if rd is None:
                rd = b''
            d = self.device.read(self.jtag_ep_in, self.jtag_ep_in.wMaxPacketSize, timeout)
            rd += bytes(d)
        bw.join()
        return rd[:in_data_size]
    
    JTAG_CMD_FLUSH = 0xa
    JTAG_CMD_RSV = 0xb
    JTAG_CMD_REP = staticmethod(lambda x: 0xc | (x & 3))
        
class Cmd:
    pass

class CmdClk(Cmd):
    def __init__(self, tms, tdi = 0, capture = False, count = 1):
        self.tms = 1 if tms else 0
        self.tdi = 1 if tdi else 0
        self.capture = 1 if capture else 0
        self.count = count

    def to_nibbles(self):
        ret = []
        count = self.count
        while count:
            cnt = min(0x10000, count)
            ret.append(self.capture << 2 | self.tms << 1 | self.tdi)
            repeat = cnt - 1
            while repeat:
                ret.append(0xc | (repeat & 3))
                repeat >>= 2
            count -= cnt
        if self.capture:
            return ret, self.count
        else:
            return ret, 0

    def __repr__(self):
        return f"<Clk m{self.tms} i{self.tdi}{' cap' if self.capture else ''} x{self.count}>"
        
class CmdRst(Cmd):
    def __init__(self, asserted):
        self.asserted = 1 if asserted else 0

    def to_nibbles(self):
        return [0x8 | self.asserted], 0

    def __repr__(self):
        return f"<Rst {self.asserted}>"

class State(enum.IntEnum):
    Unknown = 0
    Reset = 1
    Run = 2
    Pause = 3

class JtagInterface(jtag.Interface):
    def __init__(self, port):
        self.__divisor = port.div_max
        self.__divisor_dirty = True
        super().__init__(port)
        self.state = State.Unknown

        self.port.io_set(self.port.jtag_interface.bInterfaceNumber, 0x00)

    def freq_update(self, freq):
        freq = float(freq or self.port.base_freq)
        div = min(self.port.div_max, max(self.port.div_min, int(self.port.base_freq / 2 / freq)))
        self.__divisor_dirty = self.__divisor != div
        self.__divisor = div
        return self.port.base_freq / 2 / self.__divisor

    def _execute(self, operation_list):
        pending = []
        rx = {}
        rx_off = 0
        total_shift = 0

        #self.logger.protocol("Running %s %s", operation_list, self.state)
        
        if self.__divisor_dirty:
            self.port.divisor_set(self.port.jtag_interface.bInterfaceNumber, self.__divisor)
            self.__divisor_dirty = False

        for op in operation_list:
            if isinstance(op, jtag.CaptureDr):
                if self.state == State.Pause:
                    pending.append(CmdClk(tms = 1, count = 2))
                    self.state = State.Run
                    total_shift += 2
                if self.state == State.Run:
                    pending.append(CmdClk(tms = 1))
                    pending.append(CmdClk(tms = 0))
                    pending.append(CmdClk(tms = 1))
                    pending.append(CmdClk(tms = 0))
                    self.state = State.Pause
                    total_shift += 4
                else:
                    raise RuntimeError(self.state)

            elif isinstance(op, jtag.CaptureIr):
                if self.state == State.Pause:
                    pending.append(CmdClk(tms = 1, count = 2))
                    self.state = State.Run
                    total_shift += 2
                if self.state == State.Run:
                    pending.append(CmdClk(tms = 1, count = 2))
                    pending.append(CmdClk(tms = 0))
                    pending.append(CmdClk(tms = 1))
                    pending.append(CmdClk(tms = 0))
                    self.state = State.Pause
                    total_shift += 5
                else:
                    raise RuntimeError(self.state)

            elif isinstance(op, jtag.GenericOperation):
                rep = 0
                tms = None
                for i in range(len(op.tms)):
                    t = op.tms[i]
                    if t == tms:
                        rep += 1
                    else:
                        if tms is not None:
                            pending.append(CmdClk(tms = tms, count = rep))
                        rep = 1
                        tms = t
                if rep:
                    pending.append(CmdClk(tms = tms, count = rep))
                total_shift += len(op.tms)
                self.state = State.Reset

            elif isinstance(op, jtag.Shift):
                if not op.tdi:
                    pass
                elif self.state == State.Pause:
                    pending.append(CmdClk(tms = 1))
                    pending.append(CmdClk(tms = 0))
                    total_shift += 2
                    rx_start = rx_off

                    if isinstance(op.tdi, int):
                        pending.append(CmdClk(tms = 0,
                                              tdi = 0,
                                              capture = op.read_tdo,
                                              count = op.tdi - 1))
                        pending.append(CmdClk(tms = 1,
                                              tdi = 0,
                                              capture = op.read_tdo))
                        if read_tdo:
                            rx_off += op.tdi
                        total_shift += op.tdi

                    elif isinstance(op.tdi, bitstring.BitStringBase):
                        rep = 0
                        tdi = None
                        for i in range(len(op.tdi)):
                            t = op.tdi[i]
                            if t == tdi:
                                rep += 1
                            else:
                                if tdi is not None:
                                    pending.append(CmdClk(tdi = tdi,
                                                          tms = 0,
                                                          count = rep,
                                                          capture = op.read_tdo))
                                rep = 1
                                tdi = t
                        if rep > 1:
                            pending.append(CmdClk(tms = 0,
                                                  tdi = tdi,
                                                  count = rep - 1,
                                                  capture = op.read_tdo))
                            pending.append(CmdClk(tms = 1,
                                                  tdi = tdi,
                                                  count = 1,
                                                  capture = op.read_tdo))
                        elif rep == 1:
                            pending.append(CmdClk(tms = 1,
                                                  tdi = tdi,
                                                  count = 1,
                                                  capture = op.read_tdo))
                        if op.read_tdo:
                            rx_off += len(op.tdi)
                        total_shift += len(op.tdi)

                    else:
                        raise ValueError(op.tdi)
                    rx_stop = rx_off
                    if op.read_tdo:
                        rx[op] = (rx_start, rx_stop)
                    pending.append(CmdClk(tms = 0))
                    total_shift += 1
                else:
                    raise RuntimeError(self.state)

            elif isinstance(op, jtag.Run):
                if self.state in [State.Pause]:
                    pending.append(CmdClk(tms = 1, count = 2))
                    self.state = State.Run
                    total_shift += 2
                if self.state in [State.Reset, State.Run]:
                    pending.append(CmdClk(tms = 0, count = op.cycles or 1))
                    self.state = State.Run
                    total_shift += op.cycles or 1
                else:
                    raise RuntimeError(self.state)

            elif isinstance(op, base.Reset):
                pending.append(CmdRst(asserted = not op.asserted))

            else:
                raise ValueError(op)

        #self.logger.protocol("State after: %s", self.state)

        shift_secs = total_shift / (self.port.base_freq / self.__divisor)
        rx_bs = self.port.jtag_execute(pending, int(shift_secs * 1000) + 1500)
        #self.logger.protocol("Response tdo: %s", rx_bs)

        for op, (start, stop) in rx.items():
            #self.logger.protocol("%s: %s", op, rx_bs[start:stop])
            op.tdo = rx_bs[start:stop]
