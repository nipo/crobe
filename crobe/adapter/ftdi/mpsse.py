from . import api
from ...bitstring import BitString, BitStringSlice
from .ftdi import Handle
import enum

class Pin(enum.IntFlag):
    Tck = 0x0001
    Tdi = 0x0002
    Tdo = 0x0004
    Tms = 0x0008
    GpioL0 = 0x0010
    GpioL1 = 0x0020
    GpioL2 = 0x0040
    GpioL3 = 0x0080
    GpioH0 = 0x0100
    GpioH1 = 0x0200
    GpioH2 = 0x0400
    GpioH3 = 0x0800
    GpioH4 = 0x1000
    GpioH5 = 0x2000
    GpioH6 = 0x4000
    GpioH7 = 0x8000

class Engine(Handle):
    def __init__(self, device, interface):
        Handle.__init__(self, device.connection_id, interface, "MPSSE")

        self.logger.info("Using MPSSE with a %s device, MPS: %d", self.type,
                         self.max_packet_size)

        self.base_freq = 12e6 if self.type == "2232C" else 60e6
        self.can_div5 = self.type != "2232C"
        self.can_opendrain = self.type == "232H"
        self.can_adaptive = "H" in self.type
        self.can_pad = self.type in ["232H", "2232H", "4232H"]
        self.cycle_div = 2
        self.last_div = 0
        self.__freq = self.base_freq
        self.__div5 = False
        self.__divisor = 1

    def execute(self, operation_list):
        self.logger.trace("Running %s", operation_list)
        cmd_parts = []
        cmd_len = 0
        rsp_len = 0
        rsp_range = []
        time = 1.

        for op in operation_list:
            cmd, rl, cc = op.cmd_data()
            cmd_len += len(cmd)
            cmd_parts.append(cmd)
            rsp_range.append((rsp_len, rsp_len + rl))
            rsp_len += rl
            time += cc * self.__freq

            if isinstance(op, ClockDiv5):
                self.__div5 = op.enable
                self.__freq = self.base_freq / (5 if self.__div5 else 1) / self.__divisor
            elif isinstance(op, ClockDivisor):
                self.__divisor = op.divisor
                self.__freq = self.base_freq / (5 if self.__div5 else 1) / self.__divisor
                

        if rsp_len == 0:
            cmd_parts.append(bytes([api.MPSSE_GET_BITS_LOW]))
            rsp_len = 1
        cmd_parts.append(bytes([api.MPSSE_SEND_IMMEDIATE]))

        cmd = b''.join(cmd_parts)
            
        rsp = super().execute(cmd, rsp_len, time)

        for (l, r), op in zip(rsp_range, operation_list):
            if l == r:
                continue
            op.rsp_handle(rsp[l:r])

class Operation:
    def cmd_data(self):
        return b"", 0, 0.

    def rsp_handle(self, blob):
        pass

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"<{self.__class__.__name__}>"

class _SetBits(Operation):
    def __init__(self, value, oe):
        self.value = value
        self.oe = oe

    def cmd_data(self):
        return bytes([self._cmd, self.value, self.oe]), 0, 1

    def __str__(self):
        return f"<{self.__class__.__name__} {self.value:#04x}/{self.oe:#04x}>"
    
class SetBitsHigh(_SetBits):
    _cmd = api.MPSSE_SET_BITS_HIGH

class SetBitsLow(_SetBits):
    _cmd = api.MPSSE_SET_BITS_LOW

class _GetBits(Operation):
    def __init__(self):
        self.value = 0

    def cmd_data(self):
        return bytes([self._cmd]), 1, 1

    def rsp_handle(self, blob):
        self.value = blob[0]

    def __str__(self):
        return f"<{self.__class__.__name__}>"
    
class GetBitsHigh(_GetBits):
    _cmd = api.MPSSE_GET_BITS_HIGH

class GetBitsLow(_GetBits):
    _cmd = api.MPSSE_GET_BITS_LOW

class _Config(Operation):
    def cmd_data(self):
        return bytes([self._cmd]), 0, 0

    def rsp_handle(self, blob):
        pass

class _ConfigEnable(_Config):
    def __init__(self, enable):
        self.enable = enable

    def cmd_data(self):
        return bytes([self._cmd_enable if self.enable else self._cmd_disable]), 0, 0

    def __str__(self):
        return f"<{self.__class__.__name__} {'on' if self.enable else 'off'}>"
    
class Loopback(_ConfigEnable):
    _cmd_enable = api.MPSSE_LOOPBACK_ENABLE
    _cmd_disable = api.MPSSE_LOOPBACK_DISABLE

class ClockDivisor(_Config):
    def __init__(self, divisor):
        self.divisor = divisor

    def cmd_data(self):
        d = self.divisor - 1
        return bytes([api.MPSSE_CLK_DIV, d & 0xff, d >> 8]), 0, 0

    def __str__(self):
        return f"<{self.__class__.__name__} {self.divisor}>"

class SendImmediate(_Config):
    _cmd = api.MPSSE_SEND_IMMEDIATE

class WaitOnHigh(_Config):
    _cmd = api.MPSSE_WAIT_ON_HIGH

class WaitOnLow(_Config):
    _cmd = api.MPSSE_WAIT_ON_LOW

class ClockDiv5(_ConfigEnable):
    _cmd_enable = api.MPSSE_CLK_DIV5_ENABLE
    _cmd_disable = api.MPSSE_CLK_DIV5_DISABLE
    
class ThreePhase(_ConfigEnable):
    _cmd_enable = api.MPSSE_3_PHASE_ENABLE
    _cmd_disable = api.MPSSE_3_PHASE_DISABLE

class ClockBits(_Config):
    def __init__(self, count):
        assert 1 <= count <= 8
        self.count = count

    def cmd_data(self):
        return bytes([api.MPSSE_CLK_BITS, self.count - 1]), 0, self.count

    def __str__(self):
        return f"<{self.__class__.__name__} {self.count}>"

class ClockBits8(_Config):
    _cmd = api.MPSSE_CLK_BYTES

    def __init__(self, count):
        assert 1 <= count <= 65536
        self.count = count

    def cmd_data(self):
        c = self.count - 1
        return bytes([self._cmd, c & 0xff, c >> 8]), 0, self.count

    def __str__(self):
        return f"<{self.__class__.__name__} {self.count}>"

# TODO CPU Mode Read/Writes

class ClockWaitOnHigh(_Config):
    _cmd = api.MPSSE_CLK_WAIT_HIGH

class ClockWaitOnLow(_Config):
    _cmd = api.MPSSE_CLK_WAIT_LOW

class Adaptive(_ConfigEnable):
    _cmd_enable = api.MPSSE_ADAPTIVE_ENABLE
    _cmd_disable = api.MPSSE_ADAPTIVE_DISABLE

class ClockBits8OrHigh(ClockBits8):
    _cmd = api.MPSSE_CLK_BYTES_OR_HIGH

class ClockBits8OrLow(ClockBits8):
    _cmd = api.MPSSE_CLK_BYTES_OR_LOW

class OpenCollectorEn(Operation):
    def __init__(self, mask):
        self.mask = mask

    def cmd_data(self):
        return bytes([api.MPSSE_DRIVE_OPEN_COLLECTOR, self.mask & 0xff, self.mask >> 8]), 0, 1

    def __str__(self):
        return f"<{self.__class__.__name__} {self.mask:#06x}>"
    
class ShiftBits(Operation):
    def __init__(self, data, count, write_pol = "-", read_pol = "+", lsb_first = True, read = False):
        if not (1 <= count <= 8):
            raise ValueError(f"Shifting too many bits: {count}")

        self.lsb_first = lsb_first
        cmd = api.MPSSE_BITS

        data_out = b''
        if lsb_first:
            cmd |= api.MPSSE_LSB

        if write_pol != "+":
            cmd |= api.MPSSE_WRITE_NEG

        if data is not None:
            cmd |= api.MPSSE_WRITE
            data = data or 0
            if not lsb_first:
                data <<= 8 - count
            data_out = bytes([data])

        if read:
            cmd |= api.MPSSE_READ
            if read_pol != "+":
                cmd |= api.MPSSE_READ_NEG

        self.cmd = bytes([cmd, count - 1]) + data_out
        self.count = count
        self.read = read

    def cmd_data(self):
        return self.cmd, 1 if self.read else 0, self.count

    def rsp_handle(self, blob):
        if self.read:
            if self.lsb_first:
                self.data = BitString(blob[0] >> (8 - self.count), self.count)
            else:
                self.data = BitString(blob[0], self.count)
        else:
            self.data = None

    def __str__(self):
        return f"<{self.__class__.__name__} {self.count}>"

class ShiftBits8(Operation):
    def __init__(self, data_or_bytecnt, write_pol = "-", read_pol = "+", lsb_first = True, read = False):
        cmd = 0
        self.rt = bytes

        if isinstance(data_or_bytecnt, int):
            byte_count = data_or_bytecnt
            data_out = b''
        elif isinstance(data_or_bytecnt, (BitString, BitStringSlice)):
            assert (len(data_or_bytecnt) % 8) == 0
            data_out = bytes(data_or_bytecnt)
            if not lsb_first:
                data_out = data_out[::-1]
            byte_count = len(data_out)
            cmd |= api.MPSSE_WRITE
            self.rt = BitString
        else:
            assert isinstance(data_or_bytecnt, (bytes, bytearray))
            data_out = bytes(data_or_bytecnt)
            byte_count = len(data_out)
            cmd |= api.MPSSE_WRITE

        if write_pol != "+":
            cmd |= api.MPSSE_WRITE_NEG

        if not (1 <= byte_count <= 65536):
            raise ValueError(f"Shifting too many bytes: {byte_count}")

        self.lsb_first = lsb_first
        if lsb_first:
            cmd |= api.MPSSE_LSB
        if read:
            cmd |= api.MPSSE_READ
            if read_pol != "+":
                cmd |= api.MPSSE_READ_NEG
            self.read_byte_count = byte_count
        else:
            self.read_byte_count = 0
    
        self.cmd = bytes([cmd]) + (byte_count - 1).to_bytes(2, "little") + data_out
        self.byte_count = byte_count
        self.read = read

    def cmd_data(self):
        return self.cmd, self.read_byte_count, self.byte_count * 8

    def rsp_handle(self, blob):
        if self.read:
            if self.rt is bytes:
                self.data = blob
            else:
                if not self.lsb_first:
                    blob = blob[::-1]
                self.data = BitString(blob, self.byte_count * 8)
        else:
            self.data = None

    def __str__(self):
        return f"<{self.__class__.__name__} {self.byte_count}x8>"

class ShiftTms(Operation):
    def __init__(self, data, count, write_pol = "-", read_pol = "+", read = False, tdi = 0):
        if not (1 <= count <= 8):
            raise ValueError(f"Shifting too many bits: {count}")

        cmd = api.MPSSE_BITS | api.MPSSE_TMS | api.MPSSE_LSB

        if write_pol != "+":
            cmd |= api.MPSSE_WRITE_NEG
        if read:
            cmd |= api.MPSSE_READ
            if read_pol != "+":
                cmd |= api.MPSSE_READ_NEG

        self.cmd = bytes([cmd, count - 1, (data & 0x7f) | ((tdi & 1) << 7)])
        self.count = count
        self.write_pol = write_pol
        self.read_pol = read_pol
        self.read = read
        self.tms = BitString(data, count)
        self.tdi = int(bool(tdi))

    def cmd_data(self):
        return self.cmd, 1 if self.read else 0, self.count

    def rsp_handle(self, blob):
        if self.read:
            self.data = BitString(blob[0] >> (8 - self.count), self.count)
        else:
            self.data = None

    def __str__(self):
        return f"<{self.__class__.__name__} tms={str(self.tms)} tdi={self.tdi}>"

    def __add__(self, other):
        assert isinstance(other, ShiftTms)
        tms = self.tms + other.tms
        return ShiftTms(int(tms), len(tms),
                        write_pol = self.write_pol,
                        read_pol = self.read_pol,
                        read = self.read,
                        tdi = other.tdi)
