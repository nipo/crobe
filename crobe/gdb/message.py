import binascii

class Message(object):
    @staticmethod
    def unescape(data):
        ret = []
        esc = False
        for b in data:
            if esc:
                ret.append(b ^ 0x20)
                esc = False
            elif b == 0x7d:
                esc = True
            else:
                ret.append(b)
        return bytes(ret)

    @staticmethod
    def escape(data):
        ret = []
        esc = False
        for b in data:
            if b in [0x7d, 0x23, 0x24, 0x2a]:
                ret += [0x7d, b ^ 0x20]
            else:
                ret.append(b)
        return bytes(ret)

    @staticmethod
    def unframe(packet):
        if len(packet) < 4:
            ValueError("Short packet, %d bytes" % len(packet))
        if not packet.startswith(b"$"):
            ValueError("Bad packet start, expected $")
        if not packet[-3] == b"#":
            ValueError("Bad packet checksum separator, expected #")
        data = packet[1:-3]
        chk = sum(data, 0) & 0xff
        if packet[-2:] != b"%02x" % chk:
            ValueError("Bad checksum %s, expected %02x" % (packet[-2:], chk))

        return data

    @staticmethod
    def frame(data):
        chk = sum(data, 0) & 0xff
        return b'$' + data + (b'#%02x' % chk)

    @staticmethod
    def compress(data):
        parts = []
        last = None
        run = 0
        start = 0
        split_by = 98

        for i, b in enumerate(data):
            if b == last:
                run += 1
            else:
                while run > split_by:
                    parts.append([start, split_by])
                    run -= split_by
                    start += split_by
                if run >= 4:
                    if 6 <= run <= 7:
                        run = 5
                    parts.append([start, run])
                last = b
                run = 1
                start = i

        while run > split_by:
            parts.append([start, split_by])
            run -= split_by
            start += split_by
        if run >= 4:
            if 6 <= run <= 7:
                run = 5
            parts.append([start, run])

        ret = b''
        point = 0

        for start, length in parts:
            if start > point:
                ret += data[point : start]
            ret += b'%c*%c' % (data[start], 28 + length)
            point = start + length
        ret += data[point:]
        return ret
                
class Command(Message):
    def __init__(self, return_path, data):
        self.return_path = return_path
        self.data = data

    def respond(self, response):
        self.return_path.respond(self, response)
        
    @classmethod
    def from_packet(cls, return_path, packet):
        data = cls.unframe(packet)
        data = cls.unescape(data)
        return cls(return_path, data)
        
class Response(Message):
    def __init__(self, data):
        self.data = data
        
    def to_packet(self):
        if isinstance(self.data, str):
            data = self.data.encode('ascii', 'ignore')
        elif isinstance(self.data, (bytes, bytearray)):
            data = self.data
        else:
            ValueError("Unhandle response data type %s" % type(self.data))
        return self.frame(self.compress(self.escape(data)))

class Error(Response):
    def __init__(self, no):
        Response.__init__(self, "E%02x" % (no % 256))

class Ok(Response):
    def __init__(self):
        Response.__init__(self, "OK")

class HexEncodedResponse(Response):
    def __init__(self, data):
        Response.__init__(self, binascii.b2a_hex(data.encode('utf-8')))
