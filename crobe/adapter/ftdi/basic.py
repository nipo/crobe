from .. import model
from ...bitstring import BitString
from ...protocol import jtag, base, swd, spi, chipcon, i2c
from . import ftdi, api
from ...util.pretty import metric
from collections import deque
import struct
import time

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
            return None

        d = {}
        d.update(self.enumerator.defaults)
        d.update(defaults)

        self.device.reset()

        if interface_name.lower() == "jtag":
            return JtagInterface(self, **d)

        if interface_name.lower() == "cc":
            return ChipconInterface(self, **d)

        if interface_name.lower() == "spi":
            return SpiInterface(self, **d)

        if interface_name.lower() == "swd":
            return SwdInterface(self, **d)

        if interface_name.lower() == "i2c":
            return I2cInterface(self, **d)

class AdapterEnumerator(model.AutoEnumerator):
    adapter_class = Adapter

    def __init__(self, name, short_name,
                 vid = None, pid = None,
                 **defaults):
        super().__init__(name)
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
        super().start()

    def serial_mangle(self, serial):
        return serial

class BaseInterface(object):
    def __init__(self, adapter,
                 channel = "A",
                 gpio_output = 0, gpio_value = 0,
                 resetn_pin = None, reset_pin = None,
                 reset_oe_pin = None, reset_oen_pin = None,
                 reset_od_pin = None,
                 powern_pin = None, power_pin = None,
                 activityn_pin = None, activity_pin = None):
        oe = gpio_output
        val = gpio_value

        self.__reset_pin = None
        self.__reset_oe_pin = None
        self.__reset_od_pin = None
        self.__power_pin = None
        self.__activity_pin = None

        if reset_pin is not None:
            self.__reset_pin = (reset_pin, True)
            oe |= (1 << reset_pin)
        elif resetn_pin is not None:
            self.__reset_pin = (resetn_pin, False)
            oe |= (1 << resetn_pin)
            val |= (1 << resetn_pin)

        if reset_od_pin is not None:
            self.__reset_pin = (reset_od_pin, False)
            self.__reset_od_pin = reset_od_pin

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

    @property
    def reset(self):
        if self.__reset_pin is None:
            return False

        pin, polarity = self.__reset_pin
        return self.handle.gpio_get(pin) == polarity

    @reset.setter
    def reset(self, reset):
        cmd = self.cmd_reset(reset)
        if not cmd:
            self.logger.warning("Reset %s ignored", "holding" if reset else "releasing")
            return

        self.logger.info("%s reset pin", "holding" if reset else "releasing")
        self.handle.execute(cmd)

    def cmd_reset(self, reset):
        if self.__reset_pin and self.__reset_oe_pin:
            pin, polarity = self.__reset_pin
            mod = 1 << pin
            oe = int(reset) << pin
            value = int(polarity and reset) << pin

            pin, polarity = self.__reset_oe_pin
            mod |= 1 << pin
            oe |= 1 << pin
            value |= int(bool(reset) == polarity) << pin

        elif self.__reset_od_pin is not None:
            pin = self.__reset_od_pin
            mod = 1 << pin
            oe = mod if reset else 0
            value = 0

        elif self.__reset_pin:
            pin, polarity = self.__reset_pin
            mod = 1 << pin
            oe = 1 << pin
            value = int(bool(reset) == polarity) << pin

        elif self.__reset_oe_pin:
            pin, polarity = self.__reset_oe_pin
            mod = 1 << pin
            oe = 1 << pin
            value = int(bool(reset) == polarity) << pin

        else:
            return b''

        return self.handle.cmd_gpio_mask_set(mod, oe, value)

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

    def freq_update(self, freq):
        if not freq:
            freq = 60e6
        self.handle.freq = min(freq, 60e6)
        return int(self.handle.freq)

    def cmd_activity(self, value):
        if self.__activity_pin:
            pin, polarity = self.__activity_pin
            return self.handle.cmd_gpio_mask_set(1 << pin, 1 << pin,
                                                 (1 << pin) if polarity == bool(value) else 0)
        else:
            return b""

class JtagInterface(BaseInterface, jtag.Interface):
    def __init__(self, adapter, oe_pin = None, oen_pin = None, name = None, **args):
        args["gpio_output"] = (args.get("gpio_output", 0) & 0xfff0) | 0xb
        BaseInterface.__init__(self, adapter, **args)
        jtag.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

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

            while ops \
                      and sum(len(x) for x in cmd) < self.handle.max_packet_size - 48 \
                      and tdo_length < self.handle.max_packet_size - 48:
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

class I2cInterface(BaseInterface, i2c.Interface):
    def __init__(self, adapter,
                 has_scl_in = False,
                 use_open_collector = False,
                 name = None,
                 **args):
        """
        use_open_collector is only available for FT232HL (not FT4232H, not FT2232H)
        """
        args["gpio_output"] &= ~0x3
        args["gpio_value"] |= 0x3
        BaseInterface.__init__(self, adapter, **args)
        i2c.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

        self.handle.cycle_div = 3
        scl = 1
        sda = 2
        out_base = args["gpio_value"] & 0xfc
        oe_base = args["gpio_output"] & 0xfc
        self.__sda_start = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | sda])
        self.__scl_start = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | scl | sda])
        self.__scl_restart = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | scl])
        self.__sda_restart = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base])
        self.__scl_stop = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | sda])
        self.__sda_stop = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base])

        self.__sda_out = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | scl | sda])
        self.__sda_in = bytes([api.MPSSE_SET_BITS_LOW, out_base, oe_base | scl])
        
        self.__adaptive_on = bytes([api.MPSSE_ADAPTIVE_ENABLE]) if has_scl_in else b''
        self.__adaptive_off = bytes([api.MPSSE_ADAPTIVE_DISABLE]) if has_scl_in else b''

        cmd_init = bytes([api.MPSSE_3_PHASE_ENABLE])
        if use_open_collector and self.handle.can_opendrain:
            cmd_init += bytes([api.MPSSE_DRIVE_OPEN_COLLECTOR, 0x03, 0x00])
        self.handle.execute(cmd_init)

    def _cmd_read(self, size, ack_last):
        cmd_ack = bytes([
            api.MPSSE_READ | api.MPSSE_BITS,
        7]) + self.__sda_out + bytes([
            api.MPSSE_WRITE | api.MPSSE_WRITE_NEG | api.MPSSE_BITS,
            0,
            0,
        ]) + self.__sda_in
        cmd_nack = bytes([
            api.MPSSE_READ | api.MPSSE_BITS,
            7,
            api.MPSSE_WRITE | api.MPSSE_WRITE_NEG | api.MPSSE_BITS,
            0,
            0xff,
        ])

        if ack_last:
            return self.__sda_in + cmd_ack * size
        else:
            return self.__sda_in + cmd_ack * (size - 1) + cmd_nack

    def _cmd_write(self, data):
        cmd = lambda x: self.__sda_out + bytes([
            api.MPSSE_WRITE_NEG | api.MPSSE_WRITE | api.MPSSE_BITS,
            7, x]) + self.__sda_in + bytes([
            api.MPSSE_3_PHASE_DISABLE,
            api.MPSSE_WRITE_NEG | api.MPSSE_READ | api.MPSSE_READ_NEG | api.MPSSE_WRITE | api.MPSSE_BITS,
            0,
            0xff,
            api.MPSSE_3_PHASE_ENABLE,
        ])
        return b''.join(cmd(d) for d in data)

    def _cmd_start(self):
        ret = b''
        ret += self.__sda_start * 8
        ret += self.__scl_start * 8
        ret += self.__adaptive_on
        return ret

    def _cmd_restart(self):
        ret = b''
        ret += self.__adaptive_off
        ret += self.__scl_restart * 8
        ret += self.__sda_restart * 8
        ret += self.__sda_start * 8
        ret += self.__scl_start * 8
        ret += self.__adaptive_on
        return ret

    def _cmd_stop(self):
        ret = b''
        ret += self.__adaptive_off
        ret += self.__scl_stop * 8
        ret += self.__sda_stop * 8
        return ret

    def _execute(self, operation_list):
        ops = list(operation_list)
        prev = None
        cmd = bytearray()
        rsp_size = 0
        first = True

        for idx, op in enumerate(ops):
            as_prev = bool(prev) and isinstance(prev, i2c.Read) == isinstance(op, i2c.Read)

            self.logger.info("op: %s", op)

            if isinstance(op, i2c.Read):
                is_last = idx == len(ops)-1 or not isinstance(ops[idx], i2c.Read)
                if not as_prev:
                    cmd += self._cmd_start() if first else self._cmd_restart()
                    cmd += self._cmd_write(bytes([(op.addr << 1) | 1]))
                    op.__saddr_ack = rsp_size
                    rsp_size += 1
                else:
                    op.__saddr_ack = None
                cmd += self._cmd_read(op.size, not is_last)
                op.__rdata_off = rsp_size
                rsp_size += op.size

            elif isinstance(op, i2c.Write):
                if not as_prev:
                    cmd += self._cmd_start() if first else self._cmd_restart()
                    cmd += self._cmd_write(bytes([op.addr << 1]))
                    op.__saddr_ack = rsp_size
                    rsp_size += 1
                else:
                    op.__saddr_ack = None
                cmd += self._cmd_write(op.data)
                op.__ack_off = rsp_size
                rsp_size += len(op.data)
            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))

            first = False
        cmd += self._cmd_stop()

        rsp = self.handle.execute(bytes(cmd), rsp_size)

        for op in ops:
            if op.__saddr_ack is not None:
                self.logger.debug("Saddr ack at %d: %02x", op.__saddr_ack, rsp[op.__saddr_ack])
                if rsp[op.__saddr_ack] & 1:
                    raise i2c.AddressNack(op.addr)

            if isinstance(op, i2c.Read):
                op.data = bytes(rsp[op.__rdata_off:op.__rdata_off+op.size])
            elif isinstance(op, i2c.Write):
                for off in range(op.__ack_off, op.__ack_off + len(op.data) - 1):
                    if rsp[off] & 1:
                        raise i2c.DataNack()

class SwdInterface(BaseInterface, swd.Interface):
    def __init__(self, adapter, oen_pin = None, oe_pin = None, name = None, **args):
        args["gpio_output"] = (args["gpio_output"] & 0xfff0) | 0x3
        BaseInterface.__init__(self, adapter, **args)
        swd.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)
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

            while ops and sum(len(x) for x in cmd) < self.handle.max_packet_size - 48 and rsp_length < self.handle.max_packet_size - 48:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, swd.Read):
                    cmd.append(self.__cmd_oe_on1)
                    cmd.append(self.handle.cmd_out(BitString(op.cmd << 1, 9)))
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

                    if op.ap:
                        cmd.append(self.__cmd_idle8)

                    op.__ack = rsp_length, ack
                    rsp_length += sum([bc for bc, bic in ack])
                    op.__data = rsp_length, data
                    rsp_length += sum([bc for bc, bic in data])
                    op.__par = rsp_length, par
                    rsp_length += sum([bc for bc, bic in par])
                    with_rsp.append(op)

                elif isinstance(op, swd.Write):
                    cmd.append(self.handle.cmd_out(BitString(op.cmd << 1, 9)))
                    cmd.append(self.__cmd_oe_off1)
                    cmd.append(cmd_turn)
                    c, ack = self.__cmd_in3
                    cmd.append(c)
                    cmd.append(cmd_turn)
                    cmd.append(self.__cmd_oe_on1 if op.data & 1 else self.__cmd_oe_on0)
                    dparity = int(op.data)
                    dparity ^= dparity >> 16
                    dparity ^= dparity >> 8
                    dparity ^= dparity >> 4
                    dparity = (0x6996 >> (dparity & 0xf)) & 1
                    cmd.append(self.handle.cmd_out(BitString(op.data | (dparity << 32), 33)))

                    if op.ap:
                        cmd.append(self.__cmd_idle8)

                    op.__ack = rsp_length, ack
                    rsp_length += sum([bc for bc, bic in ack])
                    with_rsp.append(op)

                elif isinstance(op, swd.Wakeup):
                    cmd.append(self.__cmd_oe_on1)
                    cmd.append(self.handle.cmd_idle(op.cycles, 1))

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

        for bytec, bits in bs:
            if bits is None:
                v = int.from_bytes(rsp[base : base + bytec], byteorder = 'little')
                bits = bytec * 8
            else:
                v = rsp[base] >> (8 - bits)
            tdo |= v << tdo_len
            tdo_len += bits
        return tdo

class ChipconInterface(BaseInterface, chipcon.Interface):
    def __init__(self, adapter, oen_pin = None, oe_pin = None, name = None, **args):
        args["gpio_output"] = (args["gpio_output"] & 0xfff0) | 0x3
        BaseInterface.__init__(self, adapter, **args)
        chipcon.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)
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
        cmd_oe_on = self.cmd_oe(True, 0)
        cmd_oe_off = self.cmd_oe(False, 1)
        cmd_read_low = bytes([api.MPSSE_GET_BITS_LOW])
        cmd_stuff = bytes([api.MPSSE_WRITE | api.MPSSE_WRITE_NEG, 0, 0, 0])

        self.handle.execute(self.cmd_activity(True))

        for op in operation_list:
            if isinstance(op, chipcon.DebugInit):
                self.handle.execute(cmd_oe_off)
                self.reset = True
                self.handle.execute(bytes([api.MPSSE_WRITE | api.MPSSE_BITS | api.MPSSE_WRITE_NEG, 1, 0]))
                self.reset = False

            elif isinstance(op, chipcon.Wait):
                time.sleep(op.cycles / self.freq)

            elif isinstance(op, chipcon.Command):
                r = self.handle.execute(
                    cmd_oe_on
                    + bytes([api.MPSSE_WRITE | api.MPSSE_WRITE_NEG, len(op.command) - 1, 0])
                    + op.command
                    + cmd_oe_off
                    + cmd_read_low, 1)
                if op.rlen:
                    while r[0] & 4:
                        r = self.handle.execute(cmd_stuff + cmd_read_low, 1)
                    op.data = self.handle.execute(
                        bytes([api.MPSSE_READ | api.MPSSE_WRITE_NEG | api.MPSSE_READ_NEG, op.rlen - 1, 0]),
                        op.rlen)

            else:
                raise ValueError(op)

        self.handle.execute(self.cmd_activity(False))

class SpiInterface(BaseInterface, spi.Interface):
    MAX_PACKET_SIZE = 2048

    def __init__(self, adapter, csn_pin = None, name = None, **args):
        args["gpio_output"] = (args["gpio_output"] & 0xfff0) | 0x3
        BaseInterface.__init__(self, adapter, **args)
        spi.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

        self.__cmd_cs_on = self.handle.cmd_gpio_mask_set(
            1 << csn_pin, 1 << csn_pin, 0 << csn_pin)
        self.__cmd_cs_off = self.handle.cmd_gpio_mask_set(
            1 << csn_pin, 1 << csn_pin, 1 << csn_pin)

        self.child_add(spi.Target(self, "cs0", 0))

    MAX_PACKET_SIZE = 2048
        
    def _execute(self, operation_list):
        ops = deque(operation_list)

        while ops:
            pending = []
            cmd = b''
            rsp_length = 0

            while ops and len(cmd) < self.MAX_PACKET_SIZE - 48 and rsp_length < self.MAX_PACKET_SIZE - 48:
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
                    if op.value is not None:
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
