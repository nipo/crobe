from .. import model
from ...protocol import jtag, base
from ... import bitstring
from ...util.pretty import metric
from ..cypress import fx2
from collections import deque
import usb.core
import usb.util
import binascii
import time
import os
import math

__all__ = []

@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x0007))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x0009))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x000d))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x000f))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x0013))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x3fd, idProduct = 0x0015))
class Adapter(fx2.Adapter):
    supported_interfaces = ["jtag"]

    OP_OUTPUT_DISABLE = 0x10
    OP_OUTPUT_ENABLE = 0x18
    OP_BIT_REVERSE = 0x20
    OP_DIV_SET = 0x28
    OP_GPIO_OUT = 0x30
    OP_GPIO_IN = 0x38
    OP_VERSION_READ = 0x50
    OP_GPIO_SELECT = 0x52
    OP_SERIAL_GET = 0x42
    OP_SHIFT = 0xa6

    EP_SHIFT_OUT = 0x02
    EP_SHIFT_IN = 0x86

    def output_enable(self, en):
        self.ctrl_out(op = 0xb0,
                      value = self.OP_OUTPUT_ENABLE if en else self.OP_OUTPUT_DISABLE,
                      index = 0)

    def div_set(self, div):
        self.ctrl_out(op = 0xb0,
                      value = self.OP_DIV_SET,
                      index = div)

    @property
    def gpio(self):
        data = self.ctrl_in(op = 0xb0,
                            value = self.OP_GPIO_IN,
                            index = 0,
                            length = 1)
        return data[0]

    @gpio.setter
    def gpio(self, value):
        self.ctrl_out(op = 0xb0,
                      value = self.OP_GPIO_OUT,
                      index = value)

    def gpio_select(self, ext):
        self.ctrl_out(op = 0xb0,
                      value = self.OP_GPIO_SELECT,
                      index = ext)

    @property
    def serial(self):
        data = self.ctrl_in(op = 0xb0,
                            value = self.OP_SERIAL_GET,
                            index = 0,
                            length = 8)
        return int.from_bytes(data, "little")

    def _version_get(self, what):
        data = self.ctrl_in(op = 0xb0,
                            value = self.OP_VERSION_READ,
                            index = what,
                            length = 2)
        return int.from_bytes(data, "little")

    @property
    def cpld_version(self):
        return self._version_get(1)

    @property
    def fw_version(self):
        return self._version_get(0)

    def __init__(self, device, name):
        fx2.Adapter.__init__(self, device, name)
        self.__inited = False

    fw = {}
    fw[0x03fd0007] = "xusbdfwu.hex"
    fw[0x03fd0009] = "xusb_xup.hex"
    fw[0x03fd000d] = "xusb_emb.hex"
    fw[0x03fd000f] = "xusb_xlp.hex"
    fw[0x03fd0013] = "xusb_xp2.hex"
    fw[0x03fd0015] = "xusb_xse.hex"

    @property
    def firmware_info(self):
        return "Firmware %04x, CPLD %04x" % (self.fw_version, self.cpld_version)

    @classmethod
    def jtag_shift_tms(cls, tms):
        count = len(tms)
        cmd = b''

        for off in range(0, count, 4):
            cnt = min(4, count - off)
            c = ((0x0100 << cnt) - 0x0100) | (int(tms[off : off+4]) << 4)
            #print(cnt, hex(c))
            cmd += c.to_bytes(2, "little")
        return cmd, count, 0

    def jtag_io(self, tdi, tms, tdo_mask):
        assert len(tdi) == len(tms)

        self.ctrl_out(op = 0xb0,
                      value = self.OP_SHIFT,
                      index = len(tdi) - 1)

        tdo_bit_count = 0
        out_blob = deque()

        for off in range(0, len(tdi), 4):
            tdi_part = int(tdi[off : off+4])
            tms_part = int(tms[off : off+4])
            if tdo_mask is None:
                tdo_mask_part = 0
                tdo_count = 0
            else:
                tdo_mask_part = int(tdo_mask[off : off+4])
                tdo_count = [0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4][tdo_mask_part]

            tdo_bit_count += tdo_count
            tck_mask = (1 << min(len(tdi) - off, 4)) - 1
            ctrl = tdi_part | (tms_part << 4) | (tck_mask << 8) | (tdo_mask_part << 12)
            out_blob.append(ctrl.to_bytes(2, "little"))

        out_blob = b''.join(out_blob)

        self.bulk_out(self.EP_SHIFT_OUT, out_blob, timeout = 2)

        if tdo_bit_count:
            in_blob = self.bulk_in(self.EP_SHIFT_IN, (tdo_bit_count + 15) // 16 * 2)
            return bitstring.BitString(in_blob, tdo_bit_count)
        return bitstring.BitString(0, 0)

    def execute(self, blob, tdo_len):
        assert tdo_len % 16 == 0, tdo_len

        bit_count = len(blob) * 2

        self.logger.debug("%d bits, %d tdo", bit_count, tdo_len)

        bit_count -= 1

        self.ctrl_out(op = 0xb0,
                      value = self.OP_SHIFT | ((bit_count & 0xff0000) << 8),
                      index = bit_count & 0xff)

        self.bulk_out(self.EP_SHIFT_OUT, blob, timeout = 2)

        if tdo_len:
            in_blob = self.bulk_in(self.EP_SHIFT_IN, 2048, 1)# (tdo_len + 15) // 16 * 2)
            tdo = bitstring.BitString(in_blob, tdo_len)
            #self.logger.info("tdo: %s", tdo)
            return tdo
        
        return None

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            return None

        if not self.__inited:
            from ...loadable.object import Program
            from pkg_resources import resource_filename
            fw_name = self.fw[(self.device.idVendor << 16)
                              | self.device.idProduct]
            fn = resource_filename(__name__, fw_name)
            program = Program.from_file(fn)

            self.firmware_load(program)
            self.device.set_configuration(1)
            self.device.set_interface_altsetting(0, 1)

            self.serial_number = "%016x" % self.serial

            self.gpio = 0x8008
            self.ctrl_out(0xb0, 0x2062, 0x0080)
            self.output_enable(True)
            self.ctrl_out(0xb0, 0x2062, 0x0000)
            self.div_set(0x11)

            self.jtag_io(bitstring.BitString(0, 8),
                         bitstring.BitString(0, 8),
                         bitstring.BitString(0, 8))


            self.div_set(0x11)
            self.output_enable(1)
            self.div_set(0x12)

            self.__inited = True

        if interface_name.lower() == "jtag":
            return JtagInterface(self)

class JtagInterface(jtag.Interface):
    def __init__(self, port):
        jtag.Interface.__init__(self, port)

        self.logger.info("Versions: %s", self.port.firmware_info)
        self.__div = 0x11
        self.port.div_set(0x11)
        self.port.output_enable(1)

        self.__state = None

    # 048c
    # IMKO

    # 40c8
    # MIOK
    CMD_RTI_CAPTURE_DR = bytes([0x10, 0x03]), 2, 0
    CMD_RTI_CAPTURE_IR = bytes([0x30, 0x07]), 3, 0
    CMD_CAPTURE_PAUSE = bytes([0x10, 0x03]), 2, 0
    CMD_PAUSE_CAPTURE_DR = bytes([0x70, 0x0f]), 4, 0
    CMD_PAUSE_CAPTURE_IR = bytes([0xf0, 0x0f, 0x00, 0x01]), 5, 0
    CMD_PAUSE_SHIFT = bytes([0x10, 0x03]), 2, 0
    CMD_EXIT1_PAUSE = bytes([0x00, 0x01]), 1, 0
    CMD_PAUSE_RTI = bytes([0x30, 0x07]), 3, 0
    CMD_RESET_RTI = bytes([0x00, 0x01]), 1, 0

    MPS = 512

    def freq_update(self, freq):
        if freq is None:
            freq = 1e6
        div = 771e9 / float(freq)
        div = math.ceil(math.log2(div))
        div = max(4, min(255, div))
        self.__div = div

        self.logger.debug("Changing divisor to %d", div)

        self.port.output_enable(0)
        self.port.div_set(div)
        self.port.output_enable(1)

        return 771e9 / 2 ** self.__div

    @classmethod
    def cmd_jtag_io(cls, tdi, tms, tdo_mask):
        assert len(tdi) == len(tms)
        assert len(tdi) == len(tdo_mask)

        tdo_bit_count = 0

        out_blob = deque()

        for off in range(0, len(tdi), 4):
            tdi_part = int(tdi[off : off+4])
            tms_part = int(tms[off : off+4])
            tdo_mask_part = int(tdo_mask[off : off+4])
            tdo_count = [0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4][tdo_mask_part]
            tdo_bit_count += tdo_count

            tck_mask = (1 << min(len(tdi) - off, 4)) - 1
            ctrl = tdi_part | (tms_part << 4) | (tck_mask << 8) | (tdo_mask_part << 12)
            out_blob.append(ctrl.to_bytes(2, "little"))

        out_blob = b''.join(out_blob)

        return out_blob, len(tdi), tdo_bit_count

    @classmethod
    def jtag_shift_io(cls, tdi, read_tdo = True):
        if isinstance(tdi, int):
            tdi = bitstring.BitString(0, tdi)

        padding = (-len(tdi) if read_tdo else 0) & 0xf

        tms = bitstring.BitString(0b01, 2) + bitstring.BitString(0, len(tdi) - 1) + bitstring.BitString(0b01, 2 + padding)
        if read_tdo:
            tdo = bitstring.BitString(0, 2) + bitstring.BitString(-1, len(tdi)) + bitstring.BitString(0, 1) + bitstring.BitString(-1, padding)
        else:
            tdo = bitstring.BitString(0, len(tdi) + 3 + padding)
        tdi = bitstring.BitString(0, 2) + tdi + bitstring.BitString(0, 1 + padding)

        return cls.cmd_jtag_io(tdi, tms, tdo)

    def _execute(self, operation_list):
        to_join = []
        ops = []

        MPS = 64
        max_shift_bits = (MPS - 1) * 2

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
            elif isinstance(o, jtag.Run):
                if o.cycles > max_shift_bits:
                    for i in range(0, o.cycles, max_shift_bits):
                        ops.append(jtag.Run(min(max_shift_bits, o.cycles - i)))
                else:
                    ops.append(o)
            else:
                ops.append(o)

        #self.logger.debug("running %s", operation_list)

        assert self.__state in (self.STATE_RESET, self.STATE_PAUSE, self.STATE_RTI, None)

        while ops:
            pending = []
            cmds = []
            tdo_length = 0
            bits = 0

            while ops \
                      and sum(len(x) for x in cmds) < MPS - 48 \
                      and tdo_length < MPS - 48:
                op = ops.pop(0)
                pending.append(op)
                cmd = []

                if isinstance(op, jtag.CaptureDr):
                    if self.__state == self.STATE_RTI:
                        cmd.append(self.CMD_RTI_CAPTURE_DR)
                    elif self.__state == self.STATE_PAUSE:
                        cmd.append(self.CMD_PAUSE_CAPTURE_DR)
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    cmd.append(self.CMD_CAPTURE_PAUSE)
                    self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.CaptureIr):
                    if self.__state == self.STATE_RTI:
                        cmd.append(self.CMD_RTI_CAPTURE_IR)
                    elif self.__state == self.STATE_PAUSE:
                        cmd.append(self.CMD_PAUSE_CAPTURE_IR)
                    else:
                        raise model.ProtocolError("Bad state sequence")

                    cmd.append(self.CMD_CAPTURE_PAUSE)
                    self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Run):
                    if self.__state == self.STATE_PAUSE:
                        cmd.append(self.CMD_PAUSE_RTI)
                        self.__state = self.STATE_RTI
                    elif self.__state == self.STATE_RESET:
                        cmd.append(self.CMD_RESET_RTI)
                        self.__state = self.STATE_RTI

                    if self.__state == self.STATE_RTI:
                        if op.cycles:
                            # TODO anything shorter ?
                            cmd.append(self.port.jtag_shift_tms(bitstring.BitString(0, op.cycles)))
                    else:
                        raise model.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    cmd.append(self.port.jtag_shift_tms(op.tms))
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    assert self.__state == self.STATE_PAUSE

                    c = self.jtag_shift_io(op.tdi, op.read_tdo)
                    cmd.append(c)
                    op.__tdo = tdo_length, len(op.tdi)
                    tdo_length += c[2]

                elif isinstance(op, jtag.Pause):
                    pass

                elif isinstance(op, base.Reset):
                    pass

                else:
                    raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

                for c in cmd:
                    cmds.append(c[0])
                    bits += c[1]

            #self.logger.info("pending: %s", pending)

            tdo = self.port.execute(b''.join(cmds), tdo_length)

            if tdo is not None:
                for op in pending:
                    if isinstance(op, jtag.Shift) and op.read_tdo:
                        off, size = op.__tdo
                        op.tdo = tdo[off : off + size]

            assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE)

        for o in to_join:
            tdo = bitstring.BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo
