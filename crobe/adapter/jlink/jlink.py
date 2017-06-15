from .. import model
from .. import swd
from .. import jtag
from ... import bitstring
import struct

__all__ = ['Enumerator']

class Enumerator(model.Enumerator):
    def __init__(self):
        from . import jaylink
        model.Enumerator.__init__(self)
        self.ctx = jaylink.Context()

    def find(self, **filter):
        ret = []
        for index, d in enumerate(self.ctx.devices()):
            if "serial_number" in filter and int(filter["serial_number"]) != d.serial_number:
                continue
            if "index" in filter and filter["index"] != index:
                continue
            ret.append(Adapter(d))
        return ret

class Adapter(model.Adapter):
    def __init__(self, device):
        self.device = device
        self.serial_number = self.device.serial_number
        model.Adapter.__init__(self, "JLink %d" % self.serial_number)
        self.handle = device.open()
        
    @property
    def supported_interfaces(self):
        return [x.lower() for x in self.handle.available_interfaces]

    @property
    def firmware_info(self):
        return self.handle.firmware_version[0]

    def open(self, interface_name):
        if interface_name.upper() not in self.handle.available_interfaces:
            raise NotSupportedError("Unsupported interface %s" % interface_name)

        if interface_name == "jtag":
            return JtagInterface(self)
        elif interface_name == "swd":
            return SwdInterface(self)
        raise NotSupportedError("Unsupported interface %s" % interface_name)
        
    @property
    def speed(self):
        return self.handle.speed * 1000.

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

class JLinkInterface(object):
    @property
    def speed(self):
        return int(self.port.speed)

    @speed.setter
    def speed(self, speed):
        self.logger.info("speed: %dHz", speed)
        self.port.speed = speed

    @property
    def reset(self):
        return self.port.reset

    @reset.setter
    def reset(self, reset):
        self.port.reset = reset

    @property
    def power(self):
        return self.port.power

    @power.setter
    def power(self, power):
        self.port.power = power

class JtagInterface(jtag.Interface, JLinkInterface):
    def __init__(self, port):
        jtag.Interface.__init__(self, port)
        self.port.handle.interface = "JTAG"
        self.port.handle.tresetn = True
        self.__state = None

    def execute(self, operation_list):
        ops = [x for x in operation_list if not isinstance(x, jtag.Shift) or len(x.tdi)]

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
                        raise model.ProtocolError("Bad state sequence")

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
                        raise model.ProtocolError("Bad state sequence")

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
                        raise model.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    tms_buf += op.tms
                    tdi_buf += bitstring.BitString(-1, len(op.tms))
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    if self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_SHIFT

                    if self.__state == self.STATE_SHIFT:
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
                    raise NotSupportedError("Unknown JTAG operation %s" % type(op))

                assert len(tms_buf) == len(tdi_buf)

            self.logger.debug("tms: %s", tms_buf)
            self.logger.debug("tdi: %s", tdi_buf)
            
            tdo_blob = self.port.handle.jtag_io(tms_buf.data, tdi_buf.data, len(tms_buf))
            tdo_buf = bitstring.BitString(tdo_blob, len(tms_buf))

            self.logger.debug("tdo: %s", tdo_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, jtag.Shift) and op.read_tdo:
                    op.tdo = tdo_buf[op.__offset : op.__offset + len(op.tdi)]

            assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE)

class SwdInterface(swd.Interface, JLinkInterface):
    def __init__(self, port):
        swd.Interface.__init__(self, port)
        self.port.handle.interface = "SWD"

    def execute(self, operation_list):
        ops = list(operation_list)

        self.logger.debug("running %s", ops)
        
        while ops:
            oe_buf = bitstring.BitString()
            out_buf = bitstring.BitString()
            pending = []

            while ops and len(out_buf) < 4032:
                op = ops.pop(0)
                pending.append(op)
                op.__offset = len(out_buf)

                # Out: _SpRaax_P.-------------------------------------.
                # In:  _-------.OWFddddddddddddddddddddddddddddddddp.._
                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1

                    oe_buf.append(0x4000000001ff, 1 + 8 + 4 + 33 + 1)
                    out_buf.append((ap << 2) | (addr << 4) | (parity << 6) | 0x10a,
                                   1 + 8 + 4 + 33 + 1)

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

                    oe_buf.append(0x7fffffffc1ff, 1 + 8 + 5 + 33)
                    out_buf.append((ap << 2) | (addr << 4) | (parity << 6) | 0x102
                                   | (op.data << 14) | (dparity << 46),
                                   1 + 8 + 5 + 33)

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
                    raise NotSupportedError("Unknown SWD operation %s" % type(op))

                assert len(out_buf) == len(oe_buf)

            self.logger.debug("out: %s", out_buf)
            self.logger.debug("oe : %s", oe_buf)
            
            in_blob = self.port.handle.swd_io(out_buf.data, oe_buf.data, len(out_buf))
            in_buf = bitstring.BitString(in_blob, len(out_buf))

            self.logger.debug("in : %s", in_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, (swd.Read, swd.Write)):
                    ack = in_buf[op.__offset + 9 : op.__offset + 12]
                    if int(ack) != 1:
                        self.logger.error("While running %s%s", pending[:idx+1], ("..." if idx < len(pending)-1 else ""))
                        self.logger.error("Got ACK/Wait/Error = %s", ack)
                        raise model.ProtocolError()

                    if isinstance(op, swd.Read):
                        op.data = int(in_buf[op.__offset + 12 : op.__offset + 44])
        
