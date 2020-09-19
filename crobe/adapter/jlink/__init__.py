from .. import model
from collections import deque
from ...protocol import swd, jtag, base, spi
from ... import bitstring
from ...util.pretty import metric
from ...util.endian import bitswap8
import struct
from . import backend

__all__ = []

class JLinkInterface(object):
    def __init__(self, device, interface):
        self.handle = device.handle_get()
        if interface == "spi":
            interface = "jtag"
        self.handle.interface = backend.Tif[interface.capitalize()]

    def max_speed_set(self):
        self.freq_cap("hardware", self.handle.speed_range[1])

    def freq_update(self, freq):
        if freq is None:
            self.handle.speed_khz = None
            return self.handle.speed_range[1]
        else:
            self.handle.speed_khz = float(freq) / 1000.
            return int(self.handle.speed_khz * 1000.)

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
            
            tdo_buf = self.handle.jtag_io(tms_buf, tdi_buf)

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
        JLinkInterface.__init__(self, port, "SWD")
        swd.Interface.__init__(self, port)
        self.max_speed_set()

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

            while ops and used < 512 - 16:
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
                    c = (op.cycles + 7) // 8
                    oe_list.append(b"\xff" * c)
                    out_list.append(b'\xff' * c)
                    used += c

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

            in_blob = self.handle.jtag_io(oe, out)

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

        self.child_add(spi.Target(self, "cs0", 0))

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
                        cs_pending += (b"\x00" if self.__cs is not None else b"\xff") * len(mosi)
                        out_pending += bitswap8(mosi)
                    elif isinstance(mosi, int):
                        cs_pending += (b"\x00" if self.__cs is not None else b"\xff") * mosi
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

            in_blob = self.handle.jtag_io(cs_pending, out_pending)

            for op in pending:
                if isinstance(op, spi.Shift) and op.read_miso:
                    if isinstance(op.mosi, int):
                        cl = op.mosi
                    else:
                        cl = len(op.mosi)
                    op.miso = bitswap8(in_blob[op.__offset : op.__offset + cl])
    
PIDS = [0x0101, 0x0102, 0x0103, 0x0104, 0x0105, 0x0107, 0x0108,
	0x1010, 0x1011, 0x1012, 0x1013, 0x1014, 0x1015, 0x1016,
	0x1017, 0x1018, 0x1020, 0x1055]
@model.UsbEnumerator.db.register(*[model.UsbInfo(idVendor = 0x1366, idProduct = p) for p in PIDS])
class JLink(model.Adapter):
    @classmethod
    def from_device(cls, dev):
        from usb import util
        serial = int(util.get_string(dev, dev.iSerialNumber))
        return cls(dev, serial)

    def __init__(self, device, serial):
        self.__weak_handle = lambda: None
        self._device = device
        self.serial = serial
        self.nickname = "jlink-%d" % serial
        super().__init__(self.nickname)

        self.interfaces = []
        self.firmware_info = ""

        self.__info_get_oneshot()

        intfs = [interface.name.lower() for interface in self.interfaces]
        self.supported_interfaces = intfs or ["jtag", "swd"]
        if "jtag" in self.supported_interfaces:
            self.supported_interfaces.append("spi")
        self.name = self.nickname

    def handle_get(self):
        import weakref

        handle = self.__weak_handle()
        if handle is None:
            import gc
            gc.collect()
            self.logger.info("Getting handle, as new")
            handle = backend.Handle(self._device)
            self.__weak_handle = lambda: handle
        else:
            self.logger.info("Getting handle, got %x from ref", id(handle))
            
        return handle

    def __info_get_oneshot(self):
        try:
            handle = self.handle_get()
        except:
            return

        try:
            cfg = backend.ReadConfig()
            ifs = backend.GetAvailableIf()

            handle.execute([cfg, ifs])
            self.firmware_info = handle.firmware_version
            self.interfaces = []

            nickname = cfg.data[backend.Config.Nickname : backend.Config.Nickname + 0x20]
            nickname = str(nickname.strip(b'\x00'), 'utf-8', 'ignore').strip()
            if nickname:
                self.nickname = nickname

            for v in backend.Tif:
                if ifs.data & (1 << v):
                    self.interfaces.append(v)

        except Exception as e:
            self.logger.debug("Exception when enumerating JLink device: %s", str(e))
        finally:
            handle.close()

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            return None

        if interface_name.lower() == "jtag":
            return JtagInterface(self)

        if interface_name.lower() == "spi":
            return SpiInterface(self)

        if interface_name.lower() == "swd":
            return SwdInterface(self)
