from . import model
from collections import deque
from .protocol import swd, jtag, base, spi
from .. import bitstring
from ..util.pretty import sci
from ..util.endian import bitswap8
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
        if 'jtag' in self.supported_interfaces and "spi" not in self.supported_interfaces:
            self.supported_interfaces.append("spi")
        self.__firmware_version = firmware_version

    @property
    def firmware_info(self):
        return self.__firmware_version[0]

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        if interface_name.lower() == "jtag":
            return JtagInterface(self)

        if interface_name.lower() == "spi":
            return SpiInterface(self)

        if interface_name.lower() == "swd":
            return SwdInterface(self)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class JLinkInterface(object):
    def __init__(self, device, interface):
        self.handle = device.device.open()
        self.handle.interface = interface.upper()

    def max_speed_set(self):
        self.freq_cap("hardware", self.handle.speed_range[1])

    @property
    def freq(self):
        return int(self.handle.speed * 1000.)

    @freq.setter
    def freq(self, freq):
        if freq is None:
            self.handle.speed = None
        else:
            self.handle.speed = float(freq) / 1000.

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

    def emucom_read(self, channel, size):
        return self.handle.emucom_read(channel, size)

    def emucom_write(self, channel, data):
        return self.handle.emucom_write(channel, data)

    def swo_start(self, baudrate, size = 2048):
        self.handle.swo_start(baudrate, size)

    def swo_stop(self):
        self.handle.swo_stop()

    def swo_read(self, size):
        return self.handle.swo_read(size)

class JtagInterface(JLinkInterface, jtag.Interface):
    def __init__(self, port):
        JLinkInterface.__init__(self, port, "JTAG")
        jtag.Interface.__init__(self, port)
        self.max_speed_set()
        self.handle.tresetn = True
        self.__state = None

    def _execute(self, operation_list):
        to_join = deque()
        ops = deque()

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
            pending = deque()

            while ops and len(tms_buf) < 4032:
                op = ops.popleft()
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

class SwdInterface(JLinkInterface, swd.Interface):
    def __init__(self, port):
        self.__turnaround_cycles = None
        self.__commands = {}
        self.max_speed_set()
        JLinkInterface.__init__(self, port, "SWD")
        swd.Interface.__init__(self, port)

    @property
    def turnaround_cycles(self):
        return self.__turnaround_cycles

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        self.__turnaround_cycles = cycles
        for ap in (0, 1):
            for addr in range(4):
                # Read
                #      01234567N123
                # Out: _SpRaax_P.-------------------------------------.
                # In:  _-------.OWFddddddddddddddddddddddddddddddddp.._
                parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1
                cmdval = (ap << 9) | (addr << 11) | (parity << 13) | 0x8500
                cmd = (cmdval >> (cycles + 2)).to_bytes(7, 'little')
                cmd_begin_mask = 0xffff >> (cycles + 2)
                cmd_end_mask = (1 << 56) - (1 << (48 + 1 + cycles))
                oe = (cmd_end_mask | cmd_begin_mask).to_bytes(7, 'little')
                self.__commands[(1, ap, addr)] = cmd, oe

                # Write
                #      012345678N123N
                # Out: _Spwaax_P.---.ddddddddddddddddddddddddddddddddp
                # In:  _--------OWF---------------------------------__
                parity = ap ^ (addr & 1) ^ (addr >> 1)
                cmdval = (ap << 17) | (addr << 19) | (parity << 21) | 0x810000
                cmd = (cmdval >> (cycles + 3 + cycles)).to_bytes(3, 'little')
                cmd_begin_mask = 0xffffff >> (cycles + 3 + cycles)
                cmd_end_mask = (1 << 64) - (1 << 24)
                oe = (cmd_end_mask | cmd_begin_mask).to_bytes(8, 'little')
                self.__commands[(0, ap, addr)] = cmd, oe
    

    def _execute(self, operation_list):
        ops = deque(operation_list)
        c = self.__turnaround_cycles

        #self.logger.debug("running %s", ops)
        
        while ops:
            oe_list = deque()
            out_list = deque()
            used = 0
            pending = deque()

            while ops and used < 2048 - 16:
                op = ops.popleft()
                pending.append(op)

                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    out, oe = self.__commands[(1, ap, addr)]
                    oe_list.append(oe)
                    out_list.append(out)

                    op.__offset = used + 1, 5
                    used += 7

                    if ap:
                        oe_list.append(b"\xff\xff")
                        out_list.append(b'\x00\x00')
                        used += 2
                    
                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))

                    dparity = (op.data ^ (op.data >> 16))
                    dparity ^= (dparity >> 8)
                    dparity ^= (dparity >> 4)
                    dparity = (0x6996 >> (dparity & 0xf)) & 1

                    out, oe = self.__commands[(0, ap, addr)]
                    oe_list.append(oe)
                    out_list.append(out + struct.pack("<LB", op.data, dparity))

                    op.__offset = used + 2, 4 - c
                    used += 8

                    if ap:
                        oe_list.append(b"\xff\xff")
                        out_list.append(b'\x00\x00')
                        used += 2

                elif isinstance(op, swd.Wakeup):
                    oe_list.append(b"\xff" * 7)
                    out_list.append(b'\xff' * 7)
                    used += 7

                elif isinstance(op, swd.Run):
                    c = (op.cycles + 7) // 8
                    oe_list.append(b"\xff" * c)
                    out_list.append(b'\x00' * c)
                    used += c

                elif isinstance(op, swd.JtagToSwd):
                    d = op.out.data
                    out_list.append(d)
                    oe_list.append(b'\xff' * len(d))
                    used += len(d)

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))

            out = b''.join(out_list)
            oe = b''.join(oe_list)

            in_blob = self.handle.swd_io(out, oe, used * 8)

            for idx, op in enumerate(pending):
                if isinstance(op, (swd.Read, swd.Write)):
                    byte, bit = op.__offset
                    try:
                        ack = swd.Ack(0x7 & (in_blob[byte] >> bit))
                    except ValueError:
                        ack = swd.Ack.INVALID

                    op.ack = ack
                    if isinstance(op, swd.Read):
                        op.data, = struct.unpack("<L", in_blob[byte + 1 : byte + 5])

class SpiInterface(JLinkInterface, spi.Interface):
    def __init__(self, port):
        JLinkInterface.__init__(self, port, "JTAG")
        spi.Interface.__init__(self, port)
        self.max_speed_set()
        self.__cs = False

    def _execute(self, operation_list):
        ops = deque(operation_list)
        
        while ops:
            cs_pending = bytearray()
            out_pending = bytearray()
            used = 0
            pending = deque()

            while ops and len(cs_pending) < 2048 - 16:
                op = ops.popleft()
                pending.append(op)

                if isinstance(op, spi.Shift):
                    op.__offset = len(out_pending)
                    mosi = op.mosi
                    if isinstance(mosi, bytes):
                        cs_pending += (b"\x00" if self.__cs else b"\xff") * len(mosi)
                        out_pending += bitswap8(mosi)
                    elif isinstance(mosi, int):
                        cs_pending += (b"\x00" if self.__cs else b"\xff") * mosi
                        out_pending += b"\x00" * mosi
                    else:
                        raise ValueError("Unhandled data type for mosi", mosi)
                    
                elif isinstance(op, spi.Cs):
                    if self.__cs != op.value:
                        self.__cs = op.value
                        cs_pending += b"\xff"
                        out_pending += b'\x00'

                else:
                    raise base.ProtocolError("Unknown SPI operation %s" % type(op))

            in_blob = self.handle.jtag_io(cs_pending, out_pending, len(out_pending) * 8)

            for op in pending:
                if isinstance(op, spi.Shift) and op.read_miso:
                    if isinstance(op.mosi, int):
                        cl = op.mosi
                    else:
                        cl = len(op.mosi)
                    op.miso = bitswap8(in_blob[op.__offset : op.__offset + cl])
