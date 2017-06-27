from .. import model
from ...bitstring import BitString
from ..protocol import jtag, base, swd
from . import ftdi
        
class Adapter(model.Adapter):
    supported_interfaces = ["jtag"]

    def __init__(self, enumerator, device):
        self.device = device
        self.enumerator = enumerator
        self.serial_number = enumerator.serial_mangle(self.device.serial)
        model.Adapter.__init__(self, "%s:%s" % (enumerator.short_name.lower(), self.serial_number or str(self.device.connection_id, 'ascii')[2:]))
        self.nickname = self.name

    @property
    def firmware_info(self):
        return self.enumerator.name

    def open(self, interface_name, **defaults):
        if not interface_name.lower() in self.supported_interfaces:
            raise NotSupportedError("Unsupported interface %s" % interface_name)

        d = {}
        d.update(self.enumerator.defaults)
        d.update(defaults)
        
        if interface_name.lower() == "jtag":
            return JtagInterface(self, **d)

        if interface_name.lower() == "swd":
            return SwdInterface(self, **d)
        
        raise NotSupportedError("Unsupported interface %s" % interface_name)

class JtagAdapterEnumerator(model.Enumerator):
    adapter_class = Adapter

    def __init__(self, name, short_name,
                 vid = None, pid = None,
                 **defaults):
        model.Enumerator.__init__(self, name)
        self.short_name = short_name
        self.defaults = defaults
        self.vid_pid = []

        
        if vid is not None and pid is not None:
            self.add(vid, pid)

    def add(self, vid, pid):
        self.vid_pid.append((vid, pid))
        
    def filter(self, adapter):
        return True
        
    def start(self):
        for vid, pid in self.vid_pid:
            for device in ftdi.Device.list_all(vid, pid):
                a = self.adapter_class(self, device)
                if not self.filter(a):
                    continue
                self.child_add(a)
        model.Enumerator.start(self)

    def serial_mangle(self, serial):
        return serial

class BaseInterface(object):
    def __init__(self, adapter,
                 channel = "A",
                 gpio_output = 0, gpio_value = 0,
                 resetn_pin = None, reset_pin = None,
                 powern_pin = None, power_pin = None,
                 activityn_pin = None, activity_pin = None):
        oe = (gpio_output & 0xfff0) | 0xb
        val = gpio_value

        self.__reset_pin = None
        self.__power_pin = None
        self.__activity_pin = None

        if reset_pin is not None:
            self.__reset_pin = (reset_pin, True)
            oe |= (1 << reset_pin)
        elif resetn_pin is not None:
            self.__reset_pin = (resetn_pin, False)
            oe |= (1 << resetn_pin)
            val |= (1 << resetn_pin)

        if power_pin is not None:
            self.__power_pin = (power_pin, True)
            oe |= (1 << power_pin)
        elif powern_pin is not None:
            self.__power_pin = (powern_pin, False)
            oe |= (1 << powern_pin)
            val |= (1 << powern_pin)

        if activity_pin is not None:
            self.__activity_pin = (activity_pin, True)
            oe |= (1 << activity_pin)
        elif activityn_pin is not None:
            self.__activity_pin = (activityn_pin, False)
            oe |= (1 << activityn_pin)
            val |= (1 << activityn_pin)
            
        self.handle = adapter.device.open(interface = channel, gpio_oe = oe, gpio_val = val)

    @property
    def reset(self):
        if self.__reset_pin is None:
            return False

        pin, polarity = self.__reset_pin
        return self.gpio_get(pin) == polarity

    @reset.setter
    def reset(self, reset):
        if self.__reset_pin is None:
            self.logger.warning("Reset %s ignored", "holding" if reset else "releasing")
            return

        self.logger.info("%s reset pin", "holding" if reset else "releasing")
        pin, polarity = self.__reset_pin
        self.handle.gpio_mask_set(1 << pin, 1 << pin,
                                  (1 << pin) if bool(reset) == polarity else 0)

    @property
    def power(self):
        if not self.__power_pin:
            return False

        pin, polarity = self.__power_pin
        return self.gpio_get(pin) == polarity

    @power.setter
    def power(self, power):
        if not self.__power_pin:
            self.logger.warning("Power %s ignored", "enabling" if power else "disabling")
            return

        self.logger.info("%s power", "enabling" if power else "disabling")
        pin, polarity = self.__power_pin
        self.handle.gpio_mask_set(1 << pin, 1 << pin,
                                  (1 << pin) if bool(reset) == polarity else 0)
        
    @property
    def speed(self):
        return int(self.handle.speed)

    @speed.setter
    def speed(self, speed):
        self.handle.speed = speed
        self.logger.info("requested speed %dHz, had %dHz", speed, self.handle.speed)

    def cmd_activity(self, value):
        if self.__activity_pin:
            pin, polarity = self.__activity_pin
            return self.handle.cmd_gpio_mask_set(1 << pin, 1 << pin,
                                                 (1 << pin) if polarity == bool(value) else 0)
        else:
            return b""
        
class JtagInterface(BaseInterface, jtag.Interface):
    def __init__(self, adapter, oe_pin = None, oen_pin = None, **args):
        jtag.Interface.__init__(self, adapter)
        BaseInterface.__init__(self, adapter, **args)

        self.__state = None

    def _execute(self, operation_list):
        to_join = []
        ops = []

        max_shift_bits = 512*8
        
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
            pending = []
            cmd = self.cmd_activity(True)
            tdo_length = 0

            while ops and len(cmd) < 1024:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, jtag.CaptureDr):
                    if self.__state == self.STATE_RTI:
                        cmd += self.handle.cmd_tms_shift(BitString(0x1, 2))
                    elif self.__state == self.STATE_PAUSE:
                        cmd += self.handle.cmd_tms_shift(BitString(0x7, 4))
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], (jtag.CaptureIr, jtag.Run, jtag.CaptureDr)):
                        # Actually lie about that, this will do the same
                        self.__state = self.STATE_PAUSE
                    else:
                        cmd += self.handle.cmd_tms_shift(BitString(1, 2))
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.CaptureIr):
                    if self.__state == self.STATE_RTI:
                        cmd += self.handle.cmd_tms_shift(BitString(0x3, 3))
                    elif self.__state == self.STATE_PAUSE:
                        cmd += self.handle.cmd_tms_shift(BitString(0xf, 5))
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    cmd += self.handle.cmd_tms_shift(BitString(0x1, 2))
                    self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Run):
                    if self.__state == self.STATE_PAUSE:
                        cmd += self.handle.cmd_tms_shift(BitString(0x3, 3))
                        self.__state = self.STATE_RTI
                    elif self.__state == self.STATE_RESET:
                        cmd += self.handle.cmd_tms_shift(BitString(0, 1))
                        self.__state = self.STATE_RTI
                        
                    if self.__state == self.STATE_RTI:
                        if op.cycles:
                            # TODO anything shorter ?
                            cmd += self.handle.cmd_tms_shift(BitString(0, op.cycles))
                    else:
                        raise model.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    cmd += self.handle.cmd_tms_shift(op.tms)
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    assert self.__state == self.STATE_PAUSE
                    if op.read_tdo:
                        blob, counts = self.handle.cmd_shift_io(op.tdi)
                        op.__counts = counts
                        op.__offset = tdo_length
                        tdo_length += sum([bc for bc, bic in counts])
                    else:
                        blob = self.handle.cmd_shift_out(op.tdi)
                    cmd += blob

                elif isinstance(op, jtag.Pause):
                    pass

                else:
                    raise base.ProtocolError("Unknown JTAG operation %s" % type(op))
                
            cmd += self.cmd_activity(False)

            tdo_blob = self.handle.execute(cmd, tdo_length)

            if tdo_length:
                for op in pending:
                    if isinstance(op, jtag.Shift) and op.read_tdo:
                        base = op.__offset
                        tdo = BitString()
                        for i, (bytec, bits) in enumerate(op.__counts):
                            if bits is None:
                                tdo += BitString(tdo_blob[base : base + bytec])
                            else:
                                assert bytec == 1
                                tdo += BitString(tdo_blob[base] >> (8 - bits), bits)
                            base += bytec
                        op.tdo = tdo

            assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE)

        for o in to_join:
            tdo = BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo

class SwdInterface(BaseInterface, swd.Interface):
    def __init__(self, adapter, oen_pin = None, oe_pin = None, **args):
        swd.Interface.__init__(self, adapter)
        BaseInterface.__init__(self, adapter, **args)
        if oen_pin is None and oe_pin is not None:
            self.oe_pin = (oe_pin, True)
        elif oe_pin is None and oen_pin is not None:
            self.oe_pin = (oen_pin, False)
        else:
            raise ValueError("Need oen_pin or oe_pin")

    def cmd_oe(self, val, tdi):
        pin, pol = self.oe_pin
        return self.handle.cmd_gpio_mask_set((1 << pin) | 2,
                                             (1 << pin) | 2,
                                              (int(bool(val) == pol) << pin) | (int(tdi) << 1))
        
    def _execute(self, operation_list):
        ops = list(operation_list)
        
        self.logger.debug("running %s", ops)

        while ops:
            pending = []

            cmd = self.cmd_activity(True)

            rsp_length = 0
            with_rsp = []

            while ops and len(cmd) < 4000:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1

                    cmd += self.cmd_oe(True, 1)
                    cmd += self.handle.cmd_out(BitString((ap << 2) | (addr << 4) | (parity << 6) | 0x10a, 9))
                    cmd += self.cmd_oe(False, 0)
                    cmd += self.handle.cmd_idle(1, 0)
                    c, ack_off = self.handle.cmd_in(36)
                    cmd += c
                    cmd += self.handle.cmd_idle(1, 0)
                    cmd += self.cmd_oe(True, 0)

                    if ap:
                        cmd += self.handle.cmd_idle(16, 0)

                    op.__ack = ack_off
                    op.__offset = rsp_length
                    rsp_length += sum([bc for bc, bic in op.__ack])
                    with_rsp.append(op)

                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1)
                    dparity = (op.data ^ (op.data >> 16))
                    dparity ^= (dparity >> 8)
                    dparity ^= (dparity >> 4)
                    dparity = (0x6996 >> (dparity & 0xf)) & 1

                    cmd += self.handle.cmd_out(BitString((ap << 2) | (addr << 4) | (parity << 6) | 0x102, 9))
                    cmd += self.cmd_oe(False, 1)
                    cmd += self.handle.cmd_idle(1, 1)
                    c, ack_off = self.handle.cmd_in(3)
                    cmd += c
                    cmd += self.handle.cmd_idle(1, 1)
                    cmd += self.cmd_oe(True, op.data & 1)
                    cmd += self.handle.cmd_out(BitString(op.data | (dparity << 32), 33))

                    if ap:
                        cmd += self.handle.cmd_idle(16, 0)

                    op.__ack = ack_off
                    op.__offset = rsp_length
                    rsp_length += sum([bc for bc, bic in op.__ack])
                    with_rsp.append(op)

                elif isinstance(op, swd.Wakeup):
                    cmd += self.cmd_oe(True, 1)
                    cmd += self.handle.cmd_idle(50, 1)

                elif isinstance(op, swd.Run):
                    cmd += self.handle.cmd_idle(op.cycles, 0)

                elif isinstance(op, swd.JtagToSwd):
                    cmd += self.handle.cmd_out(op.out)

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))
                
            cmd += self.cmd_activity(False)

            rsp = self.handle.execute(cmd, rsp_length)

            if rsp_length:
                for idx, op in enumerate(pending):
                    if op not in with_rsp:
                        continue

                    base = op.__offset
                    tdo = BitString()
                    for i, (bytec, bits) in enumerate(op.__ack):
                        if bits is None:
                            tdo += BitString(rsp[base : base + bytec])
                        else:
                            assert bytec == 1
                            tdo += BitString(rsp[base] >> (8 - bits), bits)
                        base += bytec
                    ack = int(tdo[:3])

                    if int(ack) != 1:
                        self.logger.error("While running %s%s", pending[:idx+1], ("..." if idx < len(pending)-1 else ""))
                        self.logger.error("Got ACK/Wait/Error = %s", ack)
                        raise base.ProtocolError()
                    
                    if isinstance(op, swd.Read):
                        op.data = int(tdo[3:35])
