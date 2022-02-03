from .. import model
from ...bitstring import BitString, BitStringSlice
from ...protocol import jtag, base, swd, spi, chipcon, i2c, bitbang, one_wire, smi
from . import ftdi, api, mpsse
from ...util.pretty import metric
from collections import deque
import struct
import time
import math

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
#        if not interface_name.lower() in self.supported_interfaces:
#            return None

        d = {}
        d.update(self.enumerator.defaults)
        d.update(defaults)

        # self.device.reset()

        if interface_name.lower() == "jtag":
            return JtagInterface(self, **d)

        if interface_name.lower() == "cc":
            return ChipconInterface(self, **d)

        if interface_name.lower() == "spi":
            return SpiInterface(self, **d)

        if interface_name.lower() == "swd":
            return SwdInterface(self, **d)

        if interface_name.lower() == "smi":
            return SmiInterface(self, **d)

        if interface_name.lower() == "i2c":
            return I2cInterface(self, **d)

        if interface_name.lower() == "1wire":
            return OneWireInterface(self, **d)

        if interface_name.lower() == "mpsse_bb":
            return MpsseBitbangInterface(self, **d)

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

    def cmd_trst(self, reset):
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

class PinControl:
    def __init__(self, engine_interface,
                 pin = None, n_pin = None,
                 oe_pin = None, oen_pin = None,
                 od_pin = None):
        self.engine_interface = engine_interface

        m = lambda x: (1 << x)

        if pin is not None:
            self.__mask = m(pin)
            self.__asseted = m(pin), m(pin)
            self.__deasseted = m(pin), 0
            self.__idle = 0, 0
        elif n_pin is not None:
            self.__mask = m(n_pin)
            self.__deasseted = m(n_pin), m(n_pin)
            self.__asseted = m(n_pin), 0
            self.__idle = 0, 0
        elif od_pin is not None:
            self.__mask = m(od_pin)
            self.__deasseted = 0, 0
            self.__asseted = m(od_pin), 0
            self.__idle = 0, 0
        else:
            self.__mask = 0
            self.__deasseted = 0, 0
            self.__asseted = 0, 0
            self.__idle = 0, 0

        if oe_pin is not None:
            self.__mask = m(oe_pin)
            self.__deasseted = m(oe_pin), 0
            self.__asseted = m(oe_pin), m(oe_pin)
            self.__idle = m(oe_pin), 0
        elif oen_pin is not None:
            self.__mask = m(oen_pin)
            self.__deasseted = m(oen_pin), m(oen_pin)
            self.__asseted = m(oen_pin), 0
            self.__idle = m(oen_pin), m(oen_pin)

    def cmds_set(self, asserted = None):
        if not self.__mask:
            return []
        if asserted is None:
            oe, value = self.__idle
        elif asserted:
            oe, value = self.__asseted
        else:
            oe, value = self.__deasseted
        return self.engine_interface.cmds_gpio(self.__mask, value, oe)
            
    @property
    def available(self):
        return self.__mask != 0

class EngineInterface(object):
    def __init__(self, adapter,
                 channel = "A",
                 gpio_output = 0, gpio_value = 0,
                 resetn_pin = None, reset_pin = None,
                 reset_oe_pin = None, reset_oen_pin = None,
                 reset_od_pin = None,
                 powern_pin = None, power_pin = None,
                 activityn_pin = None, activity_pin = None):
        self.__reset = PinControl(self, pin = reset_pin,
                                  n_pin = resetn_pin,
                                  oe_pin = reset_oe_pin,
                                  oen_pin = reset_oen_pin,
                                  od_pin = reset_od_pin)
        self.__power = PinControl(self, pin = power_pin, n_pin = powern_pin)
        self.__activity = PinControl(self, pin = activity_pin, n_pin = activityn_pin)
        
        self.__divisor = False, 1
        self.__divisor_dirty = True
        
        self.gpio_oe = gpio_output
        self.gpio_val = gpio_value
        
        self.handle = adapter.device.open(interface = channel, mode = "engine")

    def cmds_gpio(self, mask, value, oe, force = False):
        self.gpio_oe &= ~mask
        self.gpio_oe |= mask & oe
        self.gpio_val &= ~mask
        self.gpio_val |= mask & value

        ret = []
        if mask & 0xff00 or force:
            ret.append(mpsse.SetBitsHigh(self.gpio_val >> 8, self.gpio_oe >> 8))
        if mask & 0xff or force:
            ret.append(mpsse.SetBitsLow(self.gpio_val & 0xff, self.gpio_oe & 0xff))
        return ret

    def cmds_system_reset(self, asserted):
        ret = self.__reset.cmds_set(asserted)
        if not ret:
            self.logger.warning("Reset %s ignored", "asserting" if asserted else "deasserted")
        return ret

    def cmds_power(self, enabled):
        ret = self.__power.cmds_set(enabled)
        if not ret:
            self.logger.warning("Power %s ignored", "enabling" if enabled else "disabling")
        return ret

    def cmds_activity(self, value):
        return self.__power.cmds_set(value)

    def cmds_freq_update(self):
        if not self.__divisor_dirty:
            return []
        self.__divisor_dirty = False
        div5, div = self.__divisor
        ret = []
        if self.handle.can_div5:
            ret.append(mpsse.ClockDiv5(div5))
        ret.append(mpsse.ClockDivisor(div))
        return ret

    def freq_update(self, freq):
        if freq is None:
            freq = self.handle.base_freq
        base_freq = self.handle.base_freq / self.handle.cycle_div

        ratio = base_freq / float(freq)

        div5 = self.handle.can_div5 and ratio > 65536
        if div5:
            ratio /= 5
        div = min(max(int(math.ceil(ratio)), 1), 0x10000)

        actual_freq = self.handle.base_freq / self.handle.cycle_div / div
        if div5:
            actual_freq /= 5

        self.logger.debug("freq %s base %s half %s div5 %s div %s -> %s",
                          freq, self.handle.base_freq, self.handle.cycle_div, div5, div,
                          actual_freq)

        divisor = div5, div
        if self.__divisor != divisor:
            self.__divisor = divisor
            self.__divisor_dirty = True

        return actual_freq

    def start(self):
        # Initialize all IOs at once.
        self.__power.cmds_set(self.power)
        self.__reset.cmds_set(False)
        self.__activity.cmds_set(False)
        self.handle.execute(self.cmds_gpio(0, 0, 0, force = True))
    
    def _mpsse_run(self, operation_list):
        pre = self.cmds_freq_update() + self.cmds_activity(True)
        post = self.cmds_activity(False)
        self.handle.execute(pre + list(operation_list) + post)
    
class JtagInterface(EngineInterface, jtag.Interface):
    __cmd_rti_dr_pause = mpsse.ShiftTms(0b0101, 4)
    __cmd_rti_ir_pause = mpsse.ShiftTms(0b01011, 5)
    __cmd_update = mpsse.ShiftTms(0b11, 2)
    __cmd_pause_shift = mpsse.ShiftTms(0b01, 2)
    __cmd_exit1_pause = mpsse.ShiftTms(0b0, 1)
    __cmd_shift_end = staticmethod(lambda tdi, read = False: mpsse.ShiftTms(0b1, 1, tdi = tdi, read = read))
    __cmd_rti1 = mpsse.ShiftTms(0b0, 1)
    __cmd_reset = mpsse.ShiftTms(0b11111, 5)

    def __init__(self, adapter, oe_pin = None, oen_pin = None, name = None, **args):
        EngineInterface.__init__(self, adapter, **args)
        jtag.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)
        self.read_pol = "+"
        self.__state = None

    def freq_update(self, freq):
        # This is mostly a hack. For high clock rates, skew actual
        # sampling time to the falling edge. This gives a little extra
        # margin for propagation.
        if freq and freq >= 10e6:
            self.read_pol = '-'
        else:
            self.read_pol = '+'
        return EngineInterface.freq_update(self, freq)
        
    def start(self):
        # Dont execute, super().start() will init GPIOs
        self.cmds_gpio(mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tdo | mpsse.Pin.Tms,
                       0,
                       mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tms)
        EngineInterface.start(self)
        jtag.Interface.start(self)
        
    def _execute(self, operation_list):
        self.logger.debug("Running %s", operation_list)
        mpsse_ops = []
        tdos = {}

        assert self.__state in (self.STATE_RESET, self.STATE_PAUSE, self.STATE_RTI, None)

        for index, op in enumerate(operation_list):
            if isinstance(op, jtag.CaptureDr):
                if self.__state == self.STATE_RTI:
                    mpsse_ops.append(self.__cmd_rti_dr_pause)
                elif self.__state == self.STATE_PAUSE:
                    mpsse_ops.append(self.__cmd_update + self.__cmd_rti_dr_pause)
                else:
                    raise model.ProtocolError("Bad state sequence")
                self.__state = self.STATE_PAUSE

            elif isinstance(op, jtag.CaptureIr):
                if self.__state == self.STATE_RTI:
                    mpsse_ops.append(self.__cmd_rti_ir_pause)
                elif self.__state == self.STATE_PAUSE:
                    mpsse_ops.append(self.__cmd_update + self.__cmd_rti_ir_pause)
                else:
                    raise model.ProtocolError("Bad state sequence")
                self.__state = self.STATE_PAUSE

            elif isinstance(op, jtag.Run):
                if self.__state == self.STATE_PAUSE:
                    mpsse_ops.append(self.__cmd_update)
                    self.__state = self.STATE_RTI
                elif self.__state == self.STATE_RESET:
                    self.__state = self.STATE_RTI

                if self.__state == self.STATE_RTI:
                    assert op.cycles > 0
                    mpsse_ops.append(self.__cmd_rti1)
                    left = op.cycles - 1
                    while left >= 8:
                        c = min(left, 65536 * 8)
                        c = c & ~7
                        if self.handle.can_pad:
                            mpsse_ops.append(mpsse.ClockBits8(c // 8))
                        else:
                            mpsse_ops.append(mpsse.ShiftBits8(b'\x00' * (c // 8),
                                                              read_pol = self.read_pol))
                        left -= c
                    if left:
                        if self.handle.can_pad:
                            mpsse_ops.append(mpsse.ClockBits(left))
                        else:
                            mpsse_ops.append(mpsse.ShiftBits(0, left,
                                                              read_pol = self.read_pol))
                else:
                    self.logger.warning("Running from unknown state, passing through TLR")

                    mpsse_ops.append(self.__cmd_reset)
                    mpsse_ops.append(self.__cmd_rti1)
                    self.__state = self.STATE_RTI

            elif isinstance(op, jtag.GenericOperation):
                for off in range(0, len(op.tms), 7):
                    s = min(7, len(op.tms) - off)
                    mpsse_ops.append(mpsse.ShiftTms(int(op.tms[off:off+s]), s))
                self.__state = self.STATE_RESET

            elif isinstance(op, base.Reset):
                mpsse_ops += self.cmds_system_reset(op.asserted)

            elif isinstance(op, jtag.Shift):
                assert self.__state == self.STATE_PAUSE

                if isinstance(op.tdi, int):
                    cycle_count = op.tdi
                    data_in = None
                elif isinstance(op.tdi, bytes):
                    cycle_count = len(op.tdi) * 8
                    data_in = BitString(op.tdi)
                else:
                    assert isinstance(op.tdi, (BitString, BitStringSlice))
                    cycle_count = len(op.tdi)
                    data_in = op.tdi

                if cycle_count:
                    mpsse_ops.append(self.__cmd_pause_shift)

                    cmd_count_before = len(mpsse_ops)

                    if data_in is None and not op.read_tdo:
                        left = cycle_count - 1
                        while left >= 8:
                            c = min(left, 65536 * 8)
                            if self.handle.can_pad:
                                mpsse_ops.append(mpsse.ClockBits8(c // 8))
                            else:
                                mpsse_ops.append(mpsse.ShiftBits8(b'\x00' * (c // 8),
                                                              read_pol = self.read_pol))
                            left -= c
                        if left:
                            if self.handle.can_pad:
                                mpsse_ops.append(mpsse.ClockBits(left))
                            else:
                                mpsse_ops.append(mpsse.ShiftBits(0, left,
                                                              read_pol = self.read_pol))
                        mpsse_ops.append(self.__cmd_shift_end(read = False, tdi = 0))
                    elif data_in is None and op.read_tdo:
                        left = cycle_count - 1
                        while left >= 8:
                            c = min(left, 65536 * 8) & ~7
                            mpsse_ops.append(mpsse.ShiftBits8(None, c, read = True,
                                                              read_pol = self.read_pol))
                            left -= c
                        if left:
                            mpsse_ops.append(mpsse.ShiftBits(None, left, read = True,
                                                              read_pol = self.read_pol))
                        mpsse_ops.append(self.__cmd_shift_end(read = True, tdi = 0))
                    else:
                        left = cycle_count - 1
                        while left >= 8:
                            c = min(left, 65536 * 8) & ~7
                            mpsse_ops.append(mpsse.ShiftBits8(bytes(data_in[-1-left : -1-left+c]), c, read = True,
                                                              read_pol = self.read_pol))
                            left -= c
                        if left:
                            mpsse_ops.append(mpsse.ShiftBits(int(data_in[-1-left : -1]), left, read = True,
                                                              read_pol = self.read_pol))
                        mpsse_ops.append(self.__cmd_shift_end(read = True, tdi = data_in[-1]))

                    cmd_count_after = len(mpsse_ops)
                    tdos[index] = (cmd_count_before, cmd_count_after)

                    mpsse_ops.append(self.__cmd_exit1_pause)

            elif isinstance(op, jtag.Pause):
                pass

            else:
                raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

        self._mpsse_run(mpsse_ops)

        for op_index, (l, r) in tdos.items():
            op = operation_list[op_index]
            op.tdo = BitString()
            for mo in mpsse_ops[l:r]:
                op.tdo += mo.data

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
        
        self.__adaptive_on = bytes([api.MPSSE_ADAPTIVE_ENABLE]) if has_scl_in and self.handle.can_adaptive else b''
        self.__adaptive_off = bytes([api.MPSSE_ADAPTIVE_DISABLE]) if has_scl_in and self.handle.can_adaptive else b''

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

            self.logger.debug("op: %s", op)

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

            elif isinstance(op, base.Reset):
                cmd.append(self.cmd_trst(op.asserted))

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

class SwdInterface(EngineInterface, swd.Interface):
    def __init__(self, adapter, oen_pin = None, oe_pin = None, name = None, **args):
        EngineInterface.__init__(self, adapter, **args)
        swd.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

        if oen_pin is None and oe_pin is None:
            raise ValueError("Need oen_pin or oe_pin")

        self.__oe = PinControl(self, pin = oe_pin, n_pin = oen_pin)

    def start(self):
        # Dont execute, super().start() will init GPIOs
        self.cmds_gpio(mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tdo,
                       0,
                       mpsse.Pin.Tck | mpsse.Pin.Tdi)
        EngineInterface.start(self)
        swd.Interface.start(self)

    def _execute(self, operation_list):
        self.logger.debug("Running %s", operation_list)
        mpsse_ops = []
        tdos = {}

        for index, op in enumerate(operation_list):
            if isinstance(op, swd.Read):
                mpsse_ops += self.__oe.cmds_set(True)
                mpsse_ops.append(mpsse.ShiftBits(0, 1))
                mpsse_ops.append(mpsse.ShiftBits(op.cmd, 8))
                mpsse_ops += self.__oe.cmds_set(False)
                mpsse_ops.append(mpsse.ShiftBits(0, self.turnaround_cycles))
                ack_idx = len(mpsse_ops)
                mpsse_ops.append(mpsse.ShiftBits(None, 3, read = True))
                data_idx = len(mpsse_ops)
                mpsse_ops.append(mpsse.ShiftBits8(4, read = True))
                par_idx = len(mpsse_ops)
                mpsse_ops.append(mpsse.ShiftBits(None, 1, read = True))
                mpsse_ops.append(mpsse.ShiftBits(0, self.turnaround_cycles))
                mpsse_ops += self.__oe.cmds_set(True)

                if op.ap:
                    mpsse_ops.append(mpsse.ShiftBits(0, 8))
                else:
                    mpsse_ops.append(mpsse.ShiftBits(0, 8))

                tdos[index] = (ack_idx, data_idx, par_idx)

            elif isinstance(op, swd.Write):
                mpsse_ops += self.__oe.cmds_set(True)
                mpsse_ops.append(mpsse.ShiftBits(0, 1))
                mpsse_ops.append(mpsse.ShiftBits(op.cmd, 8))
                mpsse_ops += self.__oe.cmds_set(False)
                mpsse_ops.append(mpsse.ShiftBits(0, self.turnaround_cycles))
                ack_idx = len(mpsse_ops)
                mpsse_ops.append(mpsse.ShiftBits(None, 3, read = True))
                mpsse_ops.append(mpsse.ShiftBits(0, self.turnaround_cycles))
                mpsse_ops += self.__oe.cmds_set(True)
                mpsse_ops.append(mpsse.ShiftBits8(int(op.data).to_bytes(4, "little"), 4))
                dparity = int(op.data)
                dparity ^= dparity >> 16
                dparity ^= dparity >> 8
                dparity ^= dparity >> 4
                dparity = (0x6996 >> (dparity & 0xf)) & 1
                mpsse_ops.append(mpsse.ShiftBits(dparity, 1))

                if op.ap:
                    mpsse_ops.append(mpsse.ShiftBits(0, 8))
                else:
                    mpsse_ops.append(mpsse.ShiftBits(0, 8))

                tdos[index] = ack_idx,

            elif isinstance(op, swd.Wakeup):
                if self.handle.can_pad:
                    mpsse_ops += self.__oe.cmds_set(True)
                    c = min(op.cycles, 8)
                    mpsse_ops.append(mpsse.ShiftBits(0xff, c))
                    left = op.cycles - c
                    while left >= 8:
                        c = min(left // 8, 65536)
                        mpsse_ops.append(mpsse.ClockBits8(c))
                        left -= c * 8
                    if left:
                        mpsse_ops.append(mpsse.ClockBits(left))
                else:
                    mpsse_ops += self.__oe.cmds_set(True)
                    left = op.cycles
                    while left >= 8:
                        c = min(left, 65536 * 8)
                        mpsse_ops.append(mpsse.ShiftBits8(b'\xff' * (c // 8)))
                        left -= c
                    if left:
                        mpsse_ops.append(mpsse.ShiftBits(0xff, left))

            elif isinstance(op, swd.Run):
                if self.handle.can_pad:
                    mpsse_ops += self.__oe.cmds_set(True)
                    c = min(op.cycles, 8)
                    mpsse_ops.append(mpsse.ShiftBits(0, c))
                    left = op.cycles - c
                    while left >= 8:
                        c = min(left // 8, 65536)
                        mpsse_ops.append(mpsse.ClockBits8(c))
                        left -= c * 8
                    if left:
                        mpsse_ops.append(mpsse.ClockBits(left))
                else:
                    mpsse_ops += self.__oe.cmds_set(True)
                    left = op.cycles
                    while left >= 8:
                        c = min(left, 65536 * 8)
                        mpsse_ops.append(mpsse.ShiftBits8(b'\x00' * (c // 8)))
                        left -= c
                    if left:
                        mpsse_ops.append(mpsse.ShiftBits(0, left))

            elif isinstance(op, swd.JtagToSwd):
                mpsse_ops.append(mpsse.ShiftBits8(bytes(op.out)))

            elif isinstance(op, base.Reset):
                mpsse_ops += self.cmds_system_reset(op.asserted)

            else:
                raise base.ProtocolError("Unknown SWD operation %s" % type(op))

        self._mpsse_run(mpsse_ops)

        for op_index, rx in tdos.items():
            op = operation_list[op_index]

            try:
                ack = swd.Ack(int(mpsse_ops[rx[0]].data))
            except ValueError:
                ack = swd.Ack.INVALID
            op.ack = ack

            if isinstance(op, swd.Read):
                d = mpsse_ops[rx[1]].data
                if isinstance(d, bytes):
                    d = int.from_bytes(d, "little")
                op.data = int(d)
                dparity = int(op.data)
                dparity ^= dparity >> 16
                dparity ^= dparity >> 8
                dparity ^= dparity >> 4
                dparity = (0x6996 >> (dparity & 0xf)) & 1
                if dparity != int(mpsse_ops[rx[2]].data):
                    op.ack = swd.Ack.PARITY_ERR

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
                self.reset(True)
                self.handle.execute(bytes([api.MPSSE_WRITE | api.MPSSE_BITS | api.MPSSE_WRITE_NEG, 1, 0]))
                self.reset(False)

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

class SpiInterface(EngineInterface, spi.Interface):
    def __init__(self, adapter, csn_pin = None, name = None, **args):
        EngineInterface.__init__(self, adapter, **args)
        spi.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

        self.__cs = PinControl(self, n_pin = csn_pin)
        self.__sck = PinControl(self, pin = 0)
        self.child_add(spi.Target(self, "cs0", 0))

    def start(self):
        # Dont execute, super().start() will init GPIOs
        self.cmds_gpio(mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tdo,
                       mpsse.Pin.Tms,
                       mpsse.Pin.Tck | mpsse.Pin.Tdi)
        self.__cs.cmds_set(False)
        EngineInterface.start(self)
        spi.Interface.start(self)
        
    def _execute(self, operation_list):
        self.logger.debug("Running %s", operation_list)
        mpsse_ops = []
        tdos = {}
        write_pol = '-'
        read_pol = '+'

        for index, op in enumerate(operation_list):
            cmd_count_before = len(mpsse_ops)

            if isinstance(op, spi.Shift):
                if isinstance(op.mosi, (bytes, bytearray)):
                    for off in range(0, len(op.mosi), 65536):
                        chunk = bytes(op.mosi[off : off + 65536])
                        mpsse_ops.append(
                            mpsse.ShiftBits8(chunk,
                                             write_pol = write_pol,
                                             read_pol = read_pol,
                                             lsb_first = False,
                                             read = op.read_miso))
                elif isinstance(op.mosi, int) and op.read_miso:
                    for off in range(0, op.mosi, 65536):
                        chunk_len = min(op.mosi - off, 65536)
                        mpsse_ops.append(
                            mpsse.ShiftBits8(chunk_len,
                                             write_pol = write_pol,
                                             read_pol = read_pol,
                                             lsb_first = False,
                                             read = True))
                elif isinstance(op.mosi, int) and not op.read_miso:
                    for off in range(0, op.mosi, 65536):
                        chunk_len = min(op.mosi - off, 65536)
                        if self.handle.can_pad:
                            mpsse_ops.append(mpsse.ClockBits8(chunk_len))
                        else:
                            mpsse_ops.append(mpsse.ShiftBits8(b'\x00' * chunk_len,
                                                              write_pol = write_pol,
                                                              read_pol = read_pol))
                else:
                    raise ValueError("Unhandled data type for mosi", op.mosi)

            elif isinstance(op, base.Reset):
                mpsse_ops += self.cmds_system_reset(op.asserted)

            elif isinstance(op, spi.Cs):
                if op.value != 0:
                    mpsse_ops += self.__cs.cmds_set(False)
                if op.mode == 0:
                    mpsse_ops += self.__sck.cmds_set(False)
                    write_pol = '-'
                    read_pol = '+'
                elif op.mode == 1:
                    mpsse_ops += self.__sck.cmds_set(False)
                    write_pol = '+'
                    read_pol = '-'
                elif op.mode == 2:
                    mpsse_ops += self.__sck.cmds_set(True)
                    write_pol = '+'
                    read_pol = '-'
                else:
                    mpsse_ops += self.__sck.cmds_set(True)
                    write_pol = '-'
                    read_pol = '+'
                if op.value == 0:
                    mpsse_ops += self.__cs.cmds_set(True)

            else:
                raise base.ProtocolError("Unknown SPI operation %s" % type(op))

            cmd_count_after = len(mpsse_ops)
            tdos[index] = (cmd_count_before, cmd_count_after)

        self._mpsse_run(mpsse_ops)

        for index, op in enumerate(operation_list):
            if isinstance(op, spi.Shift) and op.read_miso:
                op.miso = BitString()
                l, r = tdos[index]
                for mo in mpsse_ops[l:r]:
                    op.miso += mo.data
                op.miso = bytes(op.miso)

class MpsseIoInfo(bitbang.IoInfo):
    def __init__(self, name, no):
        self.name = name
        self.no = no
        self.mode = bitbang.Mode.Input
        self.value = False
                    
class MpsseBitbangInterface(EngineInterface, bitbang.Interface):
    def __init__(self, adapter, channel = "A"):
        EngineInterface.__init__(self, adapter, channel = channel)
        bitbang.Interface.__init__(self, adapter, channel)
        
        self._ios = {}
        for i in range(8):
            self._ios[f"D{i}"] = MpsseIoInfo(f"D{i}", i)
            self._ios[f"C{i}"] = MpsseIoInfo(f"C{i}", i+8)
        
    def _execute(self, operation_list):
        mpsse_ops = []
        tdos = []

        for index, op in enumerate(operation_list):
            cmd_count_before = len(mpsse_ops)
            
            if isinstance(op, bitbang.IoSet):
                mask = 0
                value = 0
                oe = 0
                for iop in op.ops:
                    io = self._ios[iop.io]

                    if iop.mode is not None:
                        io.mode = iop.mode

                    if iop.value is not None:
                        m = 1 << io.no
                        mask |= m
                        if (io.mode & bitbang.Mode.D1) and iop.value:
                            value |= m
                            oe |= m
                        if (io.mode & bitbang.Mode.D0) and not iop.value:
                            oe |= m
                mpsse_ops += self.cmds_gpio(mask = mask, oe = oe, value = value)

            elif isinstance(op, bitbang.IoGet):
                needed = [False, False]
                for ion in op.ios:
                    io = self._ios[ion]
                    needed[int(io.no > 7)] = True

                for n, c in zip(needed, [mpsse.GetBitsLow, mpsse.GetBitsHigh]):
                    if not n:
                        continue
                    mpsse_ops.append(c())

            else:
                raise base.ProtocolError("Unknown BITBANG operation %s" % type(op))

            cmd_count_after = len(mpsse_ops)
            tdos.append((cmd_count_before, cmd_count_after))

        self._mpsse_run(mpsse_ops)

        for op, (before, after) in zip(operation_list, tdos):
            if not isinstance(op, bitbang.IoGet):
                continue
            rv = 0
            for cmd in mpsse_ops[before : after]:
                offset = 8 if isinstance(cmd, mpsse.GetBitsHigh) else 0
                rv |= cmd.value << offset
            op.values = {}
            for name in op.ios:
                iod = self._ios[name]
                op.values[name] = (rv >> iod.no) & 1

    def io_info(self):
        return self._ios

class OneWireInterface(EngineInterface, one_wire.Interface):
    """
    1-Wire implementation using MPSSE D1/D2 lines (data out and data
    in) with an external opendrain gate on D1. This is compatible with
    I2C adaptation for SDA line.

    This driver implements "recovery" (strongly driving DQ line up) for
    phantom powering by driving D2 line high during recovery time.
    """
    def __init__(self, adapter, name = None, **args):
        EngineInterface.__init__(self, adapter, **args)
        one_wire.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", adapter.freq_max)

    def start(self):
        self.cmds_gpio(mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tdo,
                       0,
                       mpsse.Pin.Tdi)
        EngineInterface.start(self)
        one_wire.Interface.start(self)

    def _cmds_pad(self, time):
        """
        Spill MPSSE commands to get idle DQ line for /time/
        """
        cycles = int(math.ceil(self.freq * time))
        ret = []
        while cycles >= 8:
            c = min(cycles // 8, 65536)
            ret.append(mpsse.ShiftBits8(b'\xff' * c, read = False))
            cycles -= c * 8
        if cycles:
            ret.append(mpsse.ShiftBits(0xff, cycles, read = False))
        return ret

    def _cmds_recover(self, time):
        """
        Spill MPSSE commands to get idle DQ line driven high for /time/
        """
        ret = self.cmds_gpio(mpsse.Pin.Tdo, mpsse.Pin.Tdo, mpsse.Pin.Tdo)
        ret += self._cmds_pad(time)
        ret += self.cmds_gpio(mpsse.Pin.Tdo, 0, 0)
        return ret

    def _cmds_zero(self, time):
        """
        Spill MPSSE commands to get idle DQ line driven low for /time/
        """
        cycles = int(math.ceil(self.freq * time))
        ret = []
        while cycles >= 8:
            c = min(cycles // 8, 65536)
            ret.append(mpsse.ShiftBits8(b'\x00' * c, read = False))
            cycles -= c * 8
        if cycles:
            ret.append(mpsse.ShiftBits(0, cycles, read = False))
        return ret

    def _cmds_read(self, time):
        """
        Spill MPSSE commands to get idle DQ line undrived for /time/ and read back
        """
        cycles = int(math.ceil(self.freq * time))
        ret = []
        while cycles >= 8:
            c = min(cycles // 8, 65536)
            ret.append(mpsse.ShiftBits8(b'\xff' * c, read = True))
            cycles -= c * 8
        if cycles:
            ret.append(mpsse.ShiftBits(0xff, cycles, read = True))
        return ret

    # override this one to take lower bound for tLOW1
    tLOW1 = 10e-6
    
    def _execute(self, operation_list):
        self.logger.debug("Running %s", operation_list)
        mpsse_ops = []
        tdos = []

        for index, op in enumerate(operation_list):
            read_zones = []
            if isinstance(op, one_wire.Reset):
                mpsse_ops += self._cmds_recover(self.tRSTL)
                mpsse_ops += self._cmds_zero(self.tRSTL)
                mpsse_ops += self._cmds_pad(self.tPDL)
                before = len(mpsse_ops)
                mpsse_ops += self._cmds_read(self.tRSTH)
                after = len(mpsse_ops)
                mpsse_ops += self._cmds_recover(self.tREC)

                read_zones.append((before, after))

            elif isinstance(op, one_wire.Wait):
                mpsse_ops += self._cmds_recover(op.delay)

            elif isinstance(op, one_wire.Write):
                for i in range(len(op.data)):
                    b = op.data[i]

                    if not b:
                        mpsse_ops += self._cmds_zero(self.tLOW0)
                        mpsse_ops += self._cmds_pad(self.tSLOT - self.tLOW0)
                    else:
                        mpsse_ops += self._cmds_zero(self.tLOW1)
                        mpsse_ops += self._cmds_pad(self.tSLOT - self.tLOW1)
                    mpsse_ops += self._cmds_recover(self.tREC)

            elif isinstance(op, one_wire.Read):
                for i in range(op.count):

                    mpsse_ops += self._cmds_zero(self.tLOWR)
                    before = len(mpsse_ops)
                    mpsse_ops += self._cmds_read(self.tRDV - self.tLOWR)
                    after = len(mpsse_ops)
                    mpsse_ops += self._cmds_pad(self.tRDV)
                    mpsse_ops += self._cmds_recover(self.tREC)

                    read_zones.append((before, after))

            else:
                raise base.ProtocolError("Unknown 1-Wire operation %s" % type(op))

            tdos.append(read_zones)

        self._mpsse_run(mpsse_ops)

        for rz, op in zip(tdos, operation_list):
            reads = []
            for b, a in rz:
                r = BitString()
                for x in mpsse_ops[b:a]:
                    r += x.data
                reads.append(int(r) == ((1 << len(r)) - 1))

#            self.logger.debug("%s -> %s", op, reads)

            if isinstance(op, one_wire.Reset):
                op.presence = not reads[0]

            elif isinstance(op, one_wire.Read):
                rdata = BitString()
                for r in reads:
                    rdata += BitString(int(r), 1)
                op.data = rdata

class SmiInterface(EngineInterface, smi.Interface):
    """
    SMI using TCK/TMS with IOs like SWD
    """
    def __init__(self, adapter, oen_pin = None, oe_pin = None, name = None, **args):
        EngineInterface.__init__(self, adapter, **args)
        smi.Interface.__init__(self, adapter, name)
        self.freq_cap("hardware", 5e6)

        if oen_pin is None and oe_pin is None:
            raise ValueError("Need oen_pin or oe_pin")

        self.__tdi = PinControl(self, pin = 1)
        self.__oe = PinControl(self, pin = oe_pin, n_pin = oen_pin)

    def start(self):
        # Dont execute, super().start() will init GPIOs
        self.cmds_gpio(mpsse.Pin.Tck | mpsse.Pin.Tdi | mpsse.Pin.Tdo,
                       0,
                       mpsse.Pin.Tck | mpsse.Pin.Tdi)
        EngineInterface.start(self)
        smi.Interface.start(self)
    
    def _execute(self, operation_list):
        self.logger.debug("Running %s", operation_list)
        mpsse_ops = []
        tdos = {}

        for index, op in enumerate(operation_list):
            mpsse_ops += self.__tdi.cmds_set(True)
            mpsse_ops += self.__oe.cmds_set(True)
            mpsse_ops.append(mpsse.ShiftBits8(b'\xff\xff\xff\xff'))
            if isinstance(op, smi.C22Read):
                mpsse_ops.append(mpsse.ShiftBits8(((0b110110 << 10) | (op.phyad << 5) | op.addr).to_bytes(2, "big"), lsb_first = False))
                mpsse_ops += self.__oe.cmds_set(False)
                mpsse_ops.append(mpsse.ShiftBits(0, 1))
                tdos[index] = len(mpsse_ops)
                mpsse_ops.append(mpsse.ShiftBits8(2, read_pol = "-", lsb_first = False, read = True))
                mpsse_ops.append(mpsse.ShiftBits(0, 1))

            elif isinstance(op, smi.C22Write):
                mpsse_ops.append(mpsse.ShiftBits8(((0b0101 << 28) | (op.phyad << 23) | (op.addr << 18) | (0b10 << 16) | op.data).to_bytes(4, "big"), lsb_first = False))
                mpsse_ops += self.__oe.cmds_set(False)
                mpsse_ops.append(mpsse.ShiftBits(1, 1))

#            elif isinstance(op, smi.C45Read):
#                pending.append(([self.CMD_C45_READ | op.prtad, op.devad], 3, op))
#            elif isinstance(op, smi.C45Write):
#                pending.append(([self.CMD_C45_WRITE | op.prtad, op.devad, op.data >> 8, op.data & 0xff], 1, None))
#            elif isinstance(op, smi.C45Addr):
#                pending.append(([self.CMD_C45_ADDR | op.prtad, op.devad, op.addr >> 8, op.addr & 0xff], 1, None))
#            elif isinstance(op, smi.C45ReadInc):
#                pending.append(([self.CMD_C45_READINC | op.prtad, op.devad], 3, op))
            else:
                raise base.ProtocolError("Unknown SMI operation %s" % type(op))
            mpsse_ops += self.__tdi.cmds_set(True)

        self._mpsse_run(mpsse_ops)

        for index, op in enumerate(operation_list):
            if index in tdos:
                op.data = int(mpsse_ops[tdos[index]].data)
