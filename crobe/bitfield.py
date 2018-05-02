
class Field:
    def __init__(self,
                 name,
                 bitrange,
                 values = None):
        self.name = name
        self.bitrange = bitrange
        if isinstance(bitrange, tuple):
            self.pos = bitrange[0]
            if len(bitrange) == 2:
                self.width = bitrange[1] - bitrange[0] + 1
            else:
                self.width = 1
        else:
            self.pos = bitrange
            self.width = 1
        self.mask = ((1 << self.width) - 1) << self.pos
        self.values = values

    def value(self, reg_value):
        return (reg_value >> self.pos) & ((1 << self.width) - 1)

    def pretty(self, value):
        try:
            return self.values[value]
        except KeyError:
            return "0x%x (unknown)" % value

    def __lt__(self, other):
        return cmp(self.pos, other.pos)

class BinaryField(Field):
    def __init__(self, name, bit, when_0, when_1):
        Field.__init__(self, name, (bit, bit), {0: when_0, 1: when_1})

class EnableField(BinaryField):
    def __init__(self, name, bit):
        BinaryField.__init__(self, name, bit, "Disabled", "Enabled")

class DisableField(BinaryField):
    def __init__(self, name, bit):
        BinaryField.__init__(self, name, bit, "Enabled", "Disabled")

class ValueField(Field):
    def __init__(self, name, bitrange, z_offset = 0):
        Field.__init__(self, name, bitrange)
        self.z_offset = z_offset

    def pretty(self, value):
        return str(value + self.z_offset)

class Log2ValueField(Field):
    def __init__(self, name, bitrange, log_offset = 0, z_offset = 0):
        Field.__init__(self, name, bitrange)
        self.log_offset = log_offset
        self.z_offset = z_offset

    def pretty(self, value):
        return str((2. ** (value + self.log_offset)) + self.z_offset)

class Register:
    def __init__(self, value):
        self.value = value
        
    def dump(self, output = print):
        fields = list(sorted(self.fields, key = lambda x:x.pos))
        w = fields[-1].pos + fields[-1].width
        wx = (w + 3) // 4
        output(" %s, %d bits" % (self.name, w))
        output(" 0x%0*x" % (wx, self.value))
        for f in fields:
            v = f.value(self.value)
            output("   % *s % *s % 8d %s %s" % (
                wx, "%0*x" % ((f.width + 3) // 4, v << (f.pos % 4)) + " " * (f.pos // 4),
                wx, hex(v),
                v, f.name, f.pretty(v)))
