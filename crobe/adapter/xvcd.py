from . import model
from ..protocol import jtag, base
from .. import bitstring
import os
import socket
import struct

__all__ = []

class SocketClosed(Exception):
    pass

@model.HwRoot.register
class Enumerator(model.ExplicitEnumerator):
    def __init__(self):
        model.Enumerator.__init__(self, "XVC")

    def child_spawn(self, name):
        return Adapter.from_target(name)
            
class Adapter(model.Adapter):
    @classmethod
    def from_target(cls, name):
        port = name.split(":")[-1]
        hostname = name[:-len(port)-1]
        
        return cls(name, hostname, int(port))

    supported_interfaces = ["jtag"]
    nickname = "XVC"

    def __init__(self, name, hostname, port):
        self.hostname = hostname
        self.port = port
        model.Adapter.__init__(self, "xvc@%s" % name)

    @property
    def firmware_info(self):
        return "XVCD server at %s:%d" % (self.hostname, self.port)

    def open(self, interface_name):
        if interface_name.lower() == "jtag":
            return JtagInterface(self)

class JtagInterface(jtag.Interface):
    def __init__(self, port):
        jtag.Interface.__init__(self, port)
        self.__state = None
        self.__tck_period = 1e-6

        ais \
                = socket.getaddrinfo(self.port.hostname, self.port.port,
                                     0, 0, socket.IPPROTO_TCP)


        for i, (family, socktype, proto, canonname, sockaddr) in enumerate(ais):
            self.socket = socket.socket(family, socktype, proto)
            try:
                self.socket.connect(sockaddr)
            except ConnectionRefusedError:
                if i == len(ais) - 1:
                    raise
                continue
            break

    def send_command(self, response_size, *command):
        for data in command:
            while data:
                written = self.socket.send(data)
                data = data[written:]
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        rsp = b''
        while len(rsp) < response_size:
            d = self.socket.recv(response_size - len(rsp))
            if not d:
                raise SocketClosed()
            rsp += d
        return rsp

    def freq_update(self, freq):
        if not getattr(self, "socket", None):
            return 1e6
        tck_period = 1. / (freq or 1e6)
        rsp = self.send_command(4, b"settck:", struct.pack("<L", int(1e9 * tck_period)))
        tck_period_ns, = struct.unpack("<L", rsp)
        self.__tck_period = tck_period_ns * 1e-9
        return 1 / self.__tck_period

    @property
    def reset(self):
        return False

    @reset.setter
    def reset(self, reset):
        self.logger.warning("Reset %s ignored", "holding" if reset else "releasing")
        
    @property
    def power(self):
        return False

    @power.setter
    def power(self, power):
        self.logger.warning("Power %s ignored", "enabling" if power else "disabling")

    def _execute(self, operation_list):
        to_join = []
        ops = []

        max_shift_bits = 4096*8
        
        for o in operation_list:
            if isinstance(o, jtag.Shift):
                if not len(o.tdi):
                    continue
                if o.tdi and len(o.tdi) > max_shift_bits:
                    parts = []
                    for i in range(0, len(o.tdi), max_shift_bits):
                        parts.append(jtag.Shift(o.tdi[i : i + max_shift_bits], read_tdo = o.read_tdo))
                    o.__parts = parts
                    ops += parts
                    if o.read_tdo:
                        to_join.append(o)
                else:
                    ops.append(o)
            else:
                ops.append(o)

        self.logger.debug("running %s", operation_list)

        assert self.__state in (self.STATE_RESET, self.STATE_PAUSE, self.STATE_RTI, None)
        
        while ops:
            tdi_buf = bitstring.BitString()
            tms_buf = bitstring.BitString()
            pending = []

            while ops and len(tms_buf) < 4032:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, jtag.CaptureDr):
                    if self.__state == self.STATE_RTI:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                    elif self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x7, 4)
                        tdi_buf.append(0x0, 4)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0x0, 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_SHIFT
                    elif ops and isinstance(ops[0], (jtag.CaptureIr, jtag.Run, jtag.CaptureDr)):
                        # Actually lie about that, this will do the same
                        self.__state = self.STATE_PAUSE
                    else:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.CaptureIr):
                    if self.__state == self.STATE_RTI:
                        tms_buf.append(0x3, 3)
                        tdi_buf.append(0x0, 3)
                    elif self.__state == self.STATE_PAUSE:
                        tms_buf.append(0xf, 5)
                        tdi_buf.append(0x0, 5)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0x0, 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_SHIFT
                    else:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Run):
                    if self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x3, 3)
                        tdi_buf.append(0x0, 3)
                        self.__state = self.STATE_RTI
                    elif self.__state == self.STATE_RESET:
                        tms_buf.append(0, 1)
                        tdi_buf.append(0, 1)
                        self.__state = self.STATE_RTI
                        
                    if self.__state == self.STATE_RTI:
                        if op.cycles:
                            tms_buf.append(0, op.cycles)
                            tdi_buf.append(0, op.cycles)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    tms_buf += op.tms
                    tdi_buf += bitstring.BitString(-1, len(op.tms))
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    if self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_SHIFT

                    assert self.__state == self.STATE_SHIFT

                    op.__offset = len(tms_buf)
                    tdi_buf += op.tdi

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0, len(op.tdi))
                    elif ops and isinstance(ops[0], (jtag.CaptureIr, jtag.CaptureDr, jtag.Run)):
                        tms_buf.append(3 << (len(op.tdi) - 1), len(op.tdi) + 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_RTI
                    else:
                        tms_buf.append(1 << (len(op.tdi) - 1), len(op.tdi) + 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Pause):
                    pass

                else:
                    raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

                assert len(tms_buf) == len(tdi_buf)

            self.logger.debug("tms: %s", tms_buf)
            self.logger.debug("tdi: %s", tdi_buf)
            
            tdo_blob = self.send_command((len(tms_buf) + 7) // 8,
                                         b"shift:",
                                         struct.pack("<L", len(tms_buf)),
                                         tms_buf.data,
                                         tdi_buf.data)

            tdo_buf = bitstring.BitString(tdo_blob, len(tms_buf))

            self.logger.debug("tdo: %s", tdo_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, jtag.Shift) and op.read_tdo:
                    op.tdo = tdo_buf[op.__offset : op.__offset + len(op.tdi)]

        assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE), self.__state

        for o in to_join:
            tdo = bitstring.BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo
