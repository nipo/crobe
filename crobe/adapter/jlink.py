from . import model
from .protocol import swd, jtag, base
from .. import bitstring
import struct

__all__ = []

@model.Enumerator.register
class Enumerator(model.Enumerator):
    def __init__(self):
        from . import libjaylink
        model.Enumerator.__init__(self, "JLink")
        self.ctx = libjaylink.Context()

    def start(self):
        for index, d in enumerate(self.ctx.devices()):
            self.child_add(Adapter.from_device(d))

        model.Enumerator.start(self)
            
class Adapter(model.Adapter):
    @classmethod
    def from_device(cls, d):
        handle = d.open()

        address = d.usb_address
        interfaces = handle.available_interfaces
        firmware_version = handle.firmware_version
        nickname = handle.config[80:80+32].split(b"\x00")[0]
        if nickname.startswith(b"\xff"):
            nickname = b""
        nickname = str(nickname, 'utf-8', 'ignore')

        del handle

        return cls(d, address, d.serial_number, interfaces, firmware_version, nickname)

    def __init__(self, device, address, serial_number, available_interfaces, firmware_version, nickname):
        model.Adapter.__init__(self, nickname or ("jlink:%s" % serial_number))

        self.device = device
        self.address = address
        self.nickname = nickname
        self.serial_number = serial_number
        self.supported_interfaces = [x.lower() for x in available_interfaces]
        self.__firmware_version = firmware_version

    @property
    def firmware_info(self):
        return self.__firmware_version[0]

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        if interface_name.lower() == "jtag":
            return JtagInterface(self)

        if interface_name.lower() == "swd":
            return SwdInterface(self)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class JLinkInterface(object):
    def __init__(self, device, interface):
        self.handle = device.device.open()
        self.handle.interface = interface.upper()

    @property
    def speed(self):
        return int(self.handle.speed * 1000.)

    @speed.setter
    def speed(self, speed):
        self.logger.info("speed %dHz", speed)
        self.handle.speed = speed / 1000.

    @property
    def reset(self):
        return not self.handle.resetn

    @reset.setter
    def reset(self, reset):
        self.logger.info("%s target reset", ["releasing", "holding"][int(reset)])
        self.handle.resetn = not reset
        
    @property
    def power(self):
        return self.handle.power

    @power.setter
    def power(self, power):
        self.logger.info("%s target power", ["disabling", "enabling"][int(power)])
        self.handle.power = power

class JtagInterface(JLinkInterface, jtag.Interface):
    def __init__(self, port):
        JLinkInterface.__init__(self, port, "JTAG")
        jtag.Interface.__init__(self, port)
        self.handle.tresetn = True
        self.__state = None

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

        #self.logger.debug("running %s", operation_list)

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

            #self.logger.debug("tms: %s", tms_buf)
            #self.logger.debug("tdi: %s", tdi_buf)
            
            tdo_blob = self.handle.jtag_io(tms_buf.data, tdi_buf.data, len(tms_buf))
            tdo_buf = bitstring.BitString(tdo_blob, len(tms_buf))

            #self.logger.debug("tdo: %s", tdo_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, jtag.Shift) and op.read_tdo:
                    op.tdo = tdo_buf[op.__offset : op.__offset + len(op.tdi)]

        assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE), self.__state

        for o in to_join:
            tdo = bitstring.BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo

class SwdInterface(swd.Interface, JLinkInterface):
    def __init__(self, port):
        swd.Interface.__init__(self, port)
        JLinkInterface.__init__(self, port, "SWD")

    def _execute(self, operation_list):
        ops = list(operation_list)

        #self.logger.debug("running %s", ops)
        
        while ops:
            oe_buf = bitstring.BitString()
            out_buf = bitstring.BitString()
            pending = []

            while ops and len(out_buf) < 4032:
                op = ops.pop(0)
                pending.append(op)

                # Out: _SpRaax_P.-------------------------------------.
                # In:  _-------.OWFddddddddddddddddddddddddddddddddp.._
                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1

                    n = 1 + 8 + self.turnaround_cycles + 3 + 33 + self.turnaround_cycles

                    op.__offset = len(out_buf) + 1 + 8 + self.turnaround_cycles - 1
                    
                    oe_buf.append(0x1ff | (1 << (n - 1)), n)
                    out_buf.append((ap << 2) | (addr << 4) | (parity << 6) | 0x10a, n)

                    if ap:
                        oe_buf.append(-1, 16)
                        out_buf.append(0, 16)
                    
                # Out: _Spwaax_P.---.ddddddddddddddddddddddddddddddddp
                # In:  _--------OWF---------------------------------__
                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1)
                    dparity = (op.data ^ (op.data >> 16))
                    dparity ^= (dparity >> 8)
                    dparity ^= (dparity >> 4)
                    dparity = (0x6996 >> (dparity & 0xf)) & 1

                    n = 1 + 8 + self.turnaround_cycles + 3 + self.turnaround_cycles + 33
                    n2 = 1 + 8 + self.turnaround_cycles + 3 + self.turnaround_cycles
                    m = (1 << n) - (1 << n2)

                    op.__offset = len(out_buf) + 1 + 8 + self.turnaround_cycles - 1
                    
                    oe_buf.append(m | 0x1ff, n)
                    out_buf.append((ap << 2) | (addr << 4) | (parity << 6) | 0x102
                                   | (op.data << n2) | (dparity << (n2 + 32)),
                                   n)

                    if ap:
                        oe_buf.append(-1, 16)
                        out_buf.append(0, 16)

                elif isinstance(op, swd.Wakeup):
                    oe_buf.append(-1, 50)
                    out_buf.append(-1, 50)

                elif isinstance(op, swd.Run):
                    oe_buf.append(-1, op.cycles)
                    out_buf.append(0, op.cycles)

                elif isinstance(op, swd.JtagToSwd):
                    oe_buf.append(-1, len(op.out))
                    out_buf += op.out

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))

                assert len(out_buf) == len(oe_buf)

            #self.logger.debug("out: %s", out_buf)
            #self.logger.debug("oe : %s", oe_buf)
            
            in_blob = self.handle.swd_io(out_buf.data, oe_buf.data, len(out_buf))
            in_buf = bitstring.BitString(in_blob, len(out_buf))

            #self.logger.debug("in : %s", in_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, (swd.Read, swd.Write)):
                    try:
                        ack = swd.Ack(int(in_buf[op.__offset : op.__offset + 3]))
                    except ValueError:
                        ack = swd.Ack.INVALID

                    op.ack = ack
                    if isinstance(op, swd.Read):
                        op.data = int(in_buf[op.__offset + 3 : op.__offset + 35])
