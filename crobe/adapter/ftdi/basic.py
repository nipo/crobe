from .. import model
from ...bitstring import BitString
from ..protocol import jtag, base, swd, spi
from . import ftdi, api
from ...util.pretty import metric
from collections import deque
import struct

class Adapter(model.Adapter):
    supported_interfaces = ["jtag"]
    freq_max = None

    def __init__(self, enumerator, device):
        self.device = device
        self.enumerator = enumerator
        self.serial_number = enumerator.serial_mangle(self.device.serial)
        model.Adapter.__init__(self, "%s-%s" % (enumerator.short_name.lower(), self.serial_number or str(self.device.connection_id, 'ascii')[2:]))
        self.nickname = self.name

    @property
    def firmware_info(self):
        return self.enumerator.name

    def open(self, interface_name, **defaults):
        if not interface_name.lower() in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        d = {}
        d.update(self.enumerator.defaults)
        d.update(defaults)

        self.device.reset()

        if interface_name.lower() == "jtag":
            return JtagInterface(self, **d)

        if interface_name.lower() == "spi":
            return SpiInterface(self, **d)

        if interface_name.lower() == "swd":
            return SwdInterface(self, **d)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class AdapterEnumerator(model.Enumerator):
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
                 reset_oe_pin = None, reset_oen_pin = None,
                 powern_pin = None, power_pin = None,
                 activityn_pin = None, activity_pin = None):
        oe = (gpio_output & 0xfff0) | 0xb
        val = gpio_value

        self.__reset_pin = None
        self.__reset_oe_pin = None
        self.__power_pin = None
        self.__activity_pin = None

        if reset_pin is not None:
            self.__reset_pin = (reset_pin, True)
            oe |= (1 << reset_pin)
        elif resetn_pin is not None:
            self.__reset_pin = (resetn_pin, False)
            oe |= (1 << resetn_pin)
            val |= (1 << resetn_pin)

        if reset_oe_pin is not None:
            self.__reset_oe_pin = (reset_oe_pin, True)
            oe |= (1 << reset_oe_pin)
        elif reset_oen_pin is not None:
            self.__reset_oe_pin = (reset_oen_pin, False)
            oe |= (1 << reset_oen_pin)
            val |= (1 << reset_oen_pin)

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
        self.freq_cap("hardware", adapter.freq_max)

    @property
    def reset(self):
        if self.__reset_pin is None:
            return False

        pin, polarity = self.__reset_pin
        return self.handle.gpio_get(pin) == polarity

    @reset.setter
    def reset(self, reset):
        mod = 0
        oe = 0
        value = 0

        if self.__reset_pin and self.__reset_oe_pin:
            pin, polarity = self.__reset_pin
            mod |= 1 << pin
            oe |= int(reset) << pin
            value |= int(polarity and reset) << pin

            pin, polarity = self.__reset_oe_pin
            mod |= 1 << pin
            oe |= 1 << pin
            value |= int(bool(reset) == polarity) << pin

        elif self.__reset_pin:
            pin, polarity = self.__reset_pin
            mod |= 1 << pin
            oe |= 1 << pin
            value |= int(bool(reset) == polarity) << pin

        elif self.__reset_oe_pin:
            pin, polarity = self.__reset_oe_pin
            mod |= 1 << pin
            oe |= 1 << pin
            value |= int(bool(reset) == polarity) << pin

        else:
            self.logger.warning("Reset %s ignored", "holding" if reset else "releasing")
            return

        self.logger.info("%s reset pin", "holding" if reset else "releasing")

        self.handle.gpio_mask_set(mod, oe, value)

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
    def freq(self):
        return int(self.handle.freq)

    @freq.setter
    def freq(self, freq):
        if not freq:
            freq = 60e6
        self.handle.freq = min(freq, 60e6)

    def cmd_activity(self, value):
        if self.__activity_pin:
            pin, polarity = self.__activity_pin
            return self.handle.cmd_gpio_mask_set(1 << pin, 1 << pin,
                                                 (1 << pin) if polarity == bool(value) else 0)
        else:
            return b""

class JtagInterface(BaseInterface, jtag.Interface):
    def __init__(self, adapter, oe_pin = None, oen_pin = None, name = None, **args):
        jtag.Interface.__init__(self, adapter, name)
        BaseInterface.__init__(self, adapter, **args)

        self.__state = None
        self.__cmd_rti_capture_dr = self.handle.cmd_tms_shift(BitString(0x1, 2))
        self.__cmd_rti_capture_ir = self.handle.cmd_tms_shift(BitString(0x3, 3))
        self.__cmd_pause_capture_dr = self.handle.cmd_tms_shift(BitString(0x7, 4))
        self.__cmd_pause_capture_ir = self.handle.cmd_tms_shift(BitString(0xf, 5))
        self.__cmd_capture_pause = self.handle.cmd_tms_shift(BitString(1, 2))
        self.__cmd_pause_rti = self.handle.cmd_tms_shift(BitString(3, 3))
        self.__cmd_reset_rti = self.handle.cmd_tms_shift(BitString(0, 1))

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

        #self.logger.debug("running %s", operation_list)

        assert self.__state in (self.STATE_RESET, self.STATE_PAUSE, self.STATE_RTI, None)

        while ops:
            pending = []
            cmd = [self.cmd_activity(True)]
            tdo_length = 0

            while ops and len(cmd) < 1024:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, jtag.CaptureDr):
                    if self.__state == self.STATE_RTI:
                        cmd.append(self.__cmd_rti_capture_dr)
                    elif self.__state == self.STATE_PAUSE:
                        cmd.append(self.__cmd_pause_capture_dr)
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], (jtag.CaptureIr, jtag.Run, jtag.CaptureDr)):
                        # Actually lie about that, this will do the same
                        pass
                    else:
                        cmd.append(self.__cmd_capture_pause)
                    self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.CaptureIr):
                    if self.__state == self.STATE_RTI:
                        cmd.append(self.__cmd_rti_capture_ir)
                    elif self.__state == self.STATE_PAUSE:
                        cmd.append(self.__cmd_pause_capture_ir)
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], (jtag.CaptureIr, jtag.Run, jtag.CaptureDr)):
                        # Actually lie about that, this will do the same
                        pass
                    else:
                        cmd.append(self.__cmd_capture_pause)
                    self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Run):
                    if self.__state == self.STATE_PAUSE:
                        cmd.append(self.__cmd_pause_rti)
                        self.__state = self.STATE_RTI
                    elif self.__state == self.STATE_RESET:
                        cmd.append(self.__cmd_reset_rti)
                        self.__state = self.STATE_RTI

                    if self.__state == self.STATE_RTI:
                        if op.cycles:
                            # TODO anything shorter ?
                            cmd.append(self.handle.cmd_tms_shift(BitString(0, op.cycles)))
                    else:
                        raise model.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    cmd.append(self.handle.cmd_tms_shift(op.tms))
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    assert self.__state == self.STATE_PAUSE
                    if op.read_tdo:
                        blob, counts = self.handle.cmd_shift_io(op.tdi)
                        op.__tdo = tdo_length, counts
                        tdo_length += sum([bc for bc, bic in counts])
                    else:
                        blob = self.handle.cmd_shift_out(op.tdi)
                    cmd.append(blob)

                elif isinstance(op, jtag.Pause):
                    pass

                else:
                    raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

            cmd.append(self.cmd_activity(False))

            tdo_blob = self.handle.execute(b''.join(cmd), tdo_length)

            if tdo_length:
                for op in pending:
                    if isinstance(op, jtag.Shift) and op.read_tdo:
                        op.tdo = self.tdo_merge(tdo_blob, *op.__tdo)

            assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE)

        for o in to_join:
            tdo = BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo

    @staticmethod
    def tdo_merge(rsp, base, bs):
        tdo = BitString()
        for bytec, bits in bs:
            if bits is None:
                tdo += BitString(rsp[base : base + bytec])
            else:
                assert bytec == 1
                tdo += BitString(rsp[base] >> (8 - bits), bits)
            base += bytec
        return tdo

class SwdInterface(BaseInterface, swd.Interface):
    def __init__(self, adapter, oen_pin = None, oe_pin = None, name = None, **args):
        swd.Interface.__init__(self, adapter, name)
        BaseInterface.__init__(self, adapter, **args)
        if oen_pin is None and oe_pin is not None:
            self.oe_pin = (oe_pin, True)
        elif oe_pin is None and oen_pin is not None:
            self.oe_pin = (oen_pin, False)
        else:
            raise ValueError("Need oen_pin or oe_pin")

        self.__cmd_oe_on0 = self.cmd_oe(True, 0)
        self.__cmd_oe_on1 = self.cmd_oe(True, 1)
        self.__cmd_oe_off0 = self.cmd_oe(False, 0)
        self.__cmd_oe_off1 = self.cmd_oe(False, 1)
        self.__cmd_in3 = self.handle.cmd_in(3)
        self.__cmd_in32 = self.handle.cmd_in(32)
        self.__cmd_in1 = self.handle.cmd_in(1)
        self.__cmd_idle8 = self.handle.cmd_idle(8, 0)

    def cmd_oe(self, val, tdi):
        pin, pol = self.oe_pin
        return self.handle.cmd_gpio_mask_set((1 << pin) | 2,
                                             (1 << pin) | 2,
                                              (int(bool(val) == pol) << pin) | (int(tdi) << 1))

    def _execute(self, operation_list):
        ops = list(operation_list)

        #self.logger.debug("running %s", ops)
        cmd_turn = self.handle.cmd_idle(self.turnaround_cycles, 1)

        while ops:
            pending = []

            cmd = []
            cmd.append(self.cmd_activity(True))

            rsp_length = 0
            with_rsp = []

            while ops and len(cmd) < 4000:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1

                    cmd.append(self.__cmd_oe_on1)
                    cmd.append(self.handle.cmd_out(BitString((ap << 2) | (addr << 4) | (parity << 6) | 0x10a, 9)))
                    cmd.append(self.__cmd_oe_off1)
                    cmd.append(cmd_turn)
                    c, ack = self.__cmd_in3
                    cmd.append(c)
                    c, data = self.__cmd_in32
                    cmd.append(c)
                    c, par = self.__cmd_in1
                    cmd.append(c)
                    cmd.append(cmd_turn)
                    cmd.append(self.cmd_oe(True, 0))

                    if ap:
                        cmd.append(self.__cmd_idle8)

                    op.__ack = rsp_length, ack
                    rsp_length += sum([bc for bc, bic in ack])
                    op.__data = rsp_length, data
                    rsp_length += sum([bc for bc, bic in data])
                    op.__par = rsp_length, par
                    rsp_length += sum([bc for bc, bic in par])
                    with_rsp.append(op)

                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    parity = ap ^ (addr & 1) ^ (addr >> 1)
                    dparity = (op.data ^ (op.data >> 16))
                    dparity ^= (dparity >> 8)
                    dparity ^= (dparity >> 4)
                    dparity = (0x6996 >> (dparity & 0xf)) & 1

                    cmd.append(self.handle.cmd_out(BitString((ap << 2) | (addr << 4) | (parity << 6) | 0x102, 9)))
                    cmd.append(self.__cmd_oe_off1)
                    cmd.append(cmd_turn)
                    c, ack = self.__cmd_in3
                    cmd.append(c)
                    cmd.append(cmd_turn)
                    cmd.append(self.__cmd_oe_on1 if op.data & 1 else self.__cmd_oe_on0)
                    cmd.append(self.handle.cmd_out(BitString(op.data | (dparity << 32), 33)))

                    if ap:
                        cmd.append(self.__cmd_idle8)

                    op.__ack = rsp_length, ack
                    rsp_length += sum([bc for bc, bic in ack])
                    with_rsp.append(op)

                elif isinstance(op, swd.Wakeup):
                    cmd.append(self.__cmd_oe_on1)
                    cmd.append(self.handle.cmd_idle(50, 1))

                elif isinstance(op, swd.Run):
                    cmd.append(self.handle.cmd_idle(op.cycles, 0))

                elif isinstance(op, swd.JtagToSwd):
                    cmd.append(self.handle.cmd_out(op.out))

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))

            cmd.append(self.cmd_activity(False))

            rsp = self.handle.execute(b''.join(cmd), rsp_length)

            if rsp_length:
                for idx, op in enumerate(pending):
                    if op not in with_rsp:
                        continue

                    ack = self.tdo_merge(rsp, *op.__ack)

                    try:
                        ack = swd.Ack(ack)
                    except ValueError:
                        ack = swd.Ack.INVALID

                    op.ack = ack

                    if isinstance(op, swd.Read):
                        op.data = self.tdo_merge(rsp, *op.__data)

    @staticmethod
    def tdo_merge(rsp, base, bs):
        if len(bs) == 1:
            bytec, bits = bs[0]
            if bits is None:
                return int.from_bytes(rsp[base : base + bytec], byteorder = 'little')
            else:
                return rsp[base] >> (8 - bits)

        tdo = 0
        tdo_len = 0

        if len(bs) > 1:
            print(bs)

        for bytec, bits in bs:
            if bits is None:
                v = int.from_bytes(rsp[base : base + bytec], byteorder = 'little')
                bits = bytec * 8
            else:
                v = rsp[base] >> (8 - bits)
            tdo |= v << tdo_len
            tdo_len += bits
        return tdo

class SpiInterface(BaseInterface, spi.Interface):
    def __init__(self, adapter, csn_pin = None, name = None, **args):
        spi.Interface.__init__(self, adapter, name)
        BaseInterface.__init__(self, adapter, **args)

        self.__cmd_cs_on = self.handle.cmd_gpio_mask_set(
            1 << csn_pin, 1 << csn_pin, 0 << csn_pin)
        self.__cmd_cs_off = self.handle.cmd_gpio_mask_set(
            1 << csn_pin, 1 << csn_pin, 1 << csn_pin)

    def _execute(self, operation_list):
        ops = deque(operation_list)

        while ops:
            pending = []
            cmd = b''
            rsp_length = 0

            while ops and len(cmd) < 4000:
                op = ops.popleft()
                pending.append(op)

                if isinstance(op, spi.Shift):
                    if isinstance(op.mosi, (bytes, bytearray)):
                        io = api.MPSSE_WRITE_NEG | api.MPSSE_WRITE
                        if op.read_miso:
                            io |= api.MPSSE_READ
                        op.__offset = rsp_length
                        for i in range(0, len(op.mosi), 1 << 16):
                            chunk = op.mosi[i : i+(1 << 16)]
                            cmd += struct.pack("<BH", io, len(chunk) - 1) + chunk
                        if op.read_miso:
                            rsp_length += len(op.mosi)
                    elif isinstance(op.mosi, int):
                        io = api.MPSSE_READ
                        op.__offset = rsp_length
                        for i in range(0, op.mosi, 1<<16):
                            cl = min(1<<16, op.mosi - i)
                            cmd += struct.pack("<BH", io, cl - 1)
                        rsp_length += op.mosi
                    else:
                        raise ValueError("Unhandled data type for mosi", op.mosi)

                elif isinstance(op, spi.Cs):
                    if op.value:
                        cmd += self.__cmd_cs_on
                    else:
                        cmd += self.__cmd_cs_off

                else:
                    raise base.ProtocolError("Unknown SPI operation %s" % type(op))

            rsp = self.handle.execute(cmd, rsp_length)

            for op in pending:
                if isinstance(op, spi.Shift) and op.read_miso:
                    if isinstance(op.mosi, int):
                        l = op.mosi
                    else:
                        l = len(op.mosi)
                    op.miso = rsp[op.__offset : op.__offset + l]
