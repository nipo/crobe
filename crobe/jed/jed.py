from ..bitstring import BitString
import re

__doc__ = """Jedec configuration file parser."""

class Field:
    def __init__(self, type, data):
        self.type = type
        self.data = data

    def __str__(self):
        return "<Field %s %s>" % (self.type, self.data[:10])

class Lexer:
    def __init__(self, filename):
        try:
            filename.read
            self.fd = filename
        except Exception as e:
            self.fd = open(filename, "rb")

    def __iter__(self):
        s = 0
        while True:
            n = self.fd.read(1)
            if not n:
                raise StopIteration()
            if n == b'\x02':
                s += n[0]
                break

        field = None
        data = []

        for l in self.fd.readlines():
            parts = l.split(b'\x03')

            s += sum(parts[0])

            text = str(parts[0], "ascii", "ignore")

            fields = text.split('*')

            for i, f in enumerate(fields):
                f = f.strip()

                if i or not field:
                    #print("new", i, f)
                    if field:
                        yield Field(field, data)
                        field = None
                        data = []

                    if f:
                        field = f[0]
                        data = list(f[1:].split())
                elif f:
                    #print("cont", field, f)
                    data += f.split()

            if len(parts) > 1:
                if field is not None:
                    raise ValueError("ETX while in a field")
                crc = str(parts[1][:4], "ascii", "ignore")

                if int(crc, 16) != ((s+3) & 0xffff):
                    raise ValueError("Bad CRC")
                break

class Note:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return "<Note %s>" % (self.text)

class Value:
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __str__(self):
        return "<Value %s: %s>" % (self.key, self.value)

class Fuse:
    def __init__(self, number, value):
        self.number = number
        self.value = value

    def __str__(self):
        return "<Fuse %d: %s>" % (self.number, self.value)

class DeviceIdentification:
    def __init__(self, architecture, pinout):
        self.architecture = architecture
        self.pinout = pinout

    def __str__(self):
        return "<Device %d %d>" % (self.architecture, self.pinout)

class EFuseData:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<EFuse: %s>" % (self.value)

class UserData:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<UserData: %s>" % (self.value)

class SecurityFuse:
    def __init__(self, enable):
        self.enable = enable

    def __str__(self):
        return "<SecurityFuse %s>" % ("yes" if self.enable else "no")

class FuseCrc:
    def __init__(self, crc):
        self.crc = crc

    def __str__(self):
        return "<FuseCrc %04x>" % (self.crc)

class FuseDefaultState:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<Fuse Default %d>" % (self.value)

class DefaultTestCondition:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "<Test Default %d>" % (self.value)

class Parser:
    def __init__(self, lexer):
        self.lexer = lexer

    def __iter__(self):
        for f in self.lexer:
            t = f.type
            try:
                handler = getattr(self, "handle_" + t)
            except AttributeError:
                raise ValueError("Field Type %s unhandled" % t)

            for i in handler(f.data):
                yield i

    def handle_N(self, data):
        data = " ".join(data)
        if data.lower().startswith("ote "):
            data = data[4:]
        yield Note(data)

    def handle_Q(self, data):
        yield Value(data[0][0], data[0][1:])

        if data[0][0] == "F":
            self.fuse_count = int(data[0][1:])

    def handle_L(self, data):
        number = int(data[0], 10)
        bits = "".join(data[1:])
        offsets = [i for i, x in enumerate(bits) if x not in "01"]
        if offsets:
            raise ValueError("Bits are not 0 or 1: at %d: %s" % (offsets[0], bits[offsets[0]]))
        value = BitString(int(bits[::-1], 2), len(bits))
        yield Fuse(number, value)

    def handle_G(self, data):
        yield SecurityFuse(data[0] == '1')

    def handle_F(self, data):
        d = int(data[0])
        self.fuse_default = d
        yield FuseDefaultState(d)

    def handle_X(self, data):
        d = int(data[0])
        yield DefaultTestCondition(d)

    def handle_C(self, data):
        crc = int(data[0], 16)
        yield FuseCrc(crc)

    def handle_E(self, data):
        data = "".join(data)
        if data[0] == 'H':
            value = BitString(int(data[1:], 16), (len(data) - 1) * 4)
        else:
            value = BitString(int(data, 2), len(data))
        yield EFuseData(value)

    def handle_U(self, data):
        mergeddata = "".join(data)
        if data[0][0] == 'A':
            value = " ".join([data[0][1:]] + data[1:])
        if data[0][0] == 'H':
            value = BitString(int(mergeddata[1:], 16), (len(mergeddata) - 1) * 4)
        else:
            value = BitString(int(mergeddata, 2), len(mergeddata))
        yield UserData(value)

    def handle_J(self, data):
        architecture, pinout = map(int, data)
        yield DeviceIdentification(architecture, pinout)

class Jed:
    def __init__(self, filename):
        self.fuse_count = 0
        self.device_architecture = None
        self.device_pinout = None
        self.fuses = None
        self.security = None
        self.pin_count = None
        self.notes = []
        self.__fuse_default = 0
        self.__fuses = []
        self.__fuse_crc = 0

        self.__parse(filename)

    def __parse(self, filename):
        p = Parser(Lexer(filename))

        for s in p:
            if isinstance(s, Value):
                if s.key == "F":
                    self.fuse_count = int(s.value)
                if s.key == "P":
                    self.pin_count = int(s.value)
            elif isinstance(s, DeviceIdentification):
                self.device_architecture = s.architecture
                self.device_pinout = s.pinout
            elif isinstance(s, FuseCrc):
                self.__fuse_crc = s.crc
            elif isinstance(s, SecurityFuse):
                self.security = s.enable
            elif isinstance(s, Fuse):
                self.__fuses.append(s)
            elif isinstance(s, Note):
                self.notes.append(s.text)

        c = self.fuse_count
        fuse_map = BitString(-self.__fuse_default, c)
        for f in self.__fuses:
            x = BitString(fuse_map[0:f.number])
            x.append(f.value)
            x.append(fuse_map[f.number+len(f.value):c])
            fuse_map = x

        crc = sum(bytes(fuse_map), 0) & 0xffff
        if crc != self.__fuse_crc:
            raise ValueError("Bad fuse crc")

        self.fuses = fuse_map
