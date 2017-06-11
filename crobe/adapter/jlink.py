from . import model
from . import swd
from . import jtag
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
        model.Adapter.__init__(self)
        self.device = device
        self.handle = device.open()

    @property
    def supported_interfaces(self):
        return map(str.lower, self.handle.available_interfaces)

    @property
    def firmware_info(self):
        return self.handle.firmware_version[0]

    @property
    def serial_number(self):
        return str(self.device.serial_number)

    def open(self, interface_name):
        if interface_name.upper() not in self.handle.available_interfaces:
            raise NotSupportedError("Unsupported interface %s" % interface_name)

        if interface_name == "jtag":
            return JtagInterface(self)
        elif interface_name == "swd":
            return SwdInterface(self)
        raise NotSupportedError("Unsupported interface %s" % interface_name)
        
    @property
    def reset(self):
        return not self.handle.resetn

    @reset.setter
    def reset(self, reset):
        self.handle.resetn = not reset

class Interface(model.Interface):
    def __init__(self, adapter):
        self.adapter = adapter
        model.Interface.__init__(self)

    @property
    def speed(self):
        return int(self.adapter.handle.speed * 1000)

    @speed.setter
    def speed(self, speed):
        self.adapter.handle.speed = speed / 1000.

    @property
    def reset(self):
        return self.adapter.reset

    @reset.setter
    def reset(self, reset):
        self.adapter.reset = reset

class JtagInterface(jtag.Interface, Interface):
    def __init__(self, adapter):
        Interface.__init__(self, adapter)
        jtag.Interface.__init__(self)
        self.adapter.handle.interface = "JTAG"
        self.__state = "Unknown"

    def run(self, operation_list):
        raise NotImplementedError()

def bin_dump(s):
    ret = ""
    for c in s:
        ret += " " + bin(ord(c))[2:].rjust(8, "0")[::-1]
    return ret

class SwdInterface(swd.Interface, Interface):
    READ_ALIGN_SHIFT = 3
    WRITE_ALIGN_SHIFT = 5

    def __init__(self, adapter):
        Interface.__init__(self, adapter)
        swd.Interface.__init__(self)
        self.adapter.handle.interface = "SWD"

    def run(self, operation_list):
        ops = list(operation_list)

        while ops:
            oe_buf = ""
            out_buf = ""
            pending = []

            while ops and len(out_buf) < 1024 - 8:
                op = ops.pop(0)
                pending.append(op)
                op.__offset = len(out_buf)

                # byte:  00000000111111112222222233333333444444445555555566666666
                # bit:   01234567012345670123456701234567012345670123456701234567
                # Out:   ______SpRaax_P.------------------------------------._____
                # In:    ______--------OWFddddddddddddddddddddddddddddddddp.._____
                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))

                    oe_buf  += struct.pack("<H", 0xffff >> self.READ_ALIGN_SHIFT) \
                               + "\x00\x00\x00\x00\xfc\xff"
                    parity = ap ^ (addr & 1) ^ (addr >> 1) ^ 1
                    out_buf += struct.pack("<H", ((ap << 1) | (addr << 3) | (parity << 5) | 0x85) << (8 - self.READ_ALIGN_SHIFT)) \
                               + "\x00\x00\x00\x00\x00\x00"

                # byte:  00000000111111112222222233333333444444445555555566666666
                # bit:   01234567012345670123456701234567012345670123456701234567
                # Out:   ___Spwaax_P.---.ddddddddddddddddddddddddddddddddp_______
                # In:    ___--------OWF---------------------------------_________
                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))

                    oe_buf  += struct.pack("<H", 0xffff >> self.WRITE_ALIGN_SHIFT) \
                               + "\xff\xff\xff\xff\xff\xff"
                    parity = ap ^ (addr & 1) ^ (addr >> 1)
                    dparity = (op.data ^ (op.data >> 16))
                    dparity ^= (dparity >> 8)
                    dparity ^= (dparity >> 4)
                    dparity = (0x6996 >> (dparity & 0xf)) & 1
                    out_buf += struct.pack("<HLB", (((ap << 1) | (addr << 3) | (parity << 5) | 0x81) << (8 - self.WRITE_ALIGN_SHIFT)), \
                                           op.data,
                                           dparity) + "\x00"

                elif isinstance(op, swd.Wakeup):
                    oe_buf  += "\xff" * 7
                    out_buf += "\xff" * 7

                elif isinstance(op, swd.JtagToSwd):
                    oe_buf  += "\xff" * 16
                    out_buf += "\xff" * 7 + "\x9e\xe7" + "\xff" * 7

                else:
                    raise NotSupportedError("Unknown SWD operation %s" % type(op))

                assert len(out_buf) == len(oe_buf)

            #print "out:", bin_dump(out_buf)
            #print "oe :", bin_dump(oe_buf)
            
            in_buf = self.adapter.handle.swd_io(out_buf, oe_buf, len(out_buf) * 8)

            #print "in :", bin_dump(in_buf)

            for idx, op in enumerate(pending):
                ack = 1
                if isinstance(op, swd.Read):
                    op.data, = struct.unpack("<L", in_buf[op.__offset + 2 : op.__offset + 6])
                    ack = (ord(in_buf[op.__offset + 1]) >> (8 - self.READ_ALIGN_SHIFT)) & 0x7
                elif isinstance(op, swd.Write):
                    ack = (ord(in_buf[op.__offset + 1]) >> (8 - self.WRITE_ALIGN_SHIFT)) & 0x7
                if ack != 1:
                    print "While running", pending[:idx+1], ("..." if idx < len(pending)-1 else "")
                    print "Got ACK/Wait/Error =", ack
                    raise model.ProtocolError()
