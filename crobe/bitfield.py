import math

class _Field(object):
    def __init__(self, lsb, width, doc = None):
        if lsb < 0:
            raise ValueError("LSB cannot be negative")

        self.lsb = int(lsb)
        self.width = int(width)
        self.width_mask = (1 << width) - 1
        self.slice = slice(self.lsb, self.lsb + self.width)
        self.value_mask_out = ~(self.width_mask << self.lsb)
        self.doc = doc

    @property
    def msb(self):
        return self.lsb + self.width - 1
        
    def extract(self, value):
        return (value >> self.lsb) & self.width_mask

    def merge(self, register_value, value):
        to_insert = (value & self.width_mask) << self.lsb
        cleared = register_value & self.value_mask_out
        return cleared | to_insert

    def represent(self, value):
        return value

    def parse(self, value):
        return int(value)

    def get_from(self, register):
        return self.represent(register[self.slice])

    def set_to(self, register, value):
        v = self.parse(value)
        register[self.slice] = v

    def docstring(self):
        addend = f"""
{self.__class__.__name__} in bit range [{self.lsb+self.width-1}:{self.lsb}] ({self.width} bits)
"""
        return (self.doc or "") + addend

    def pretty(self, v):
        if isinstance(v, int) and v is not True and v is not False:
            return hex(v)
        return str(v)

class Field(_Field):
    def __init__(self, lsb, width, offset = 0, signed = False, doc = None):
        super().__init__(lsb, width, doc = doc)
        self.offset = offset
        self.signed = signed

    def parse(self, value):
        v = super().parse(value)
        if self.signed and v & (1 << (self.width - 1)):
            v -= 1 << (self.width - 1)
        return v - self.offset

    def represent(self, value):
        v = value + self.offset
        if self.signed and v < 0:
            v += 1 << (self.width - 1)
        return super().represent(v)

    def docstring(self):
        return super().docstring() + """
Integer value""" + (f" with offset of {self.offset}" if self.offset else "")
        
class Log2Field(Field):
    def __init__(self, lsb, width, offset = 0, log_offset = 0, doc = None):
        super().__init__(lsb, width, offset = offset, doc = doc)
        self.log_offset = log_offset

    def represent(self, value):
        return super().represent(2 ** (value + self.log_offset))

    def parse(self, value):
        return super().parse(int(math.log2(int(value)) - self.log_offset))

    def docstring(self):
        return _Field.docstring(self) + f"""
Log2 value with integer offset of {self.offset} and logarithmic offset of {self.log_offset}
value = {self.offset} + 2 ** ({self.log_offset} + field)
field = log2(value - {self.offset}) - {self.log_offset}
"""

class ScaledField(Field):
    def __init__(self, lsb, width, scale = 1, offset = 0, scale_offset = 0, doc = None):
        super().__init__(lsb, width, offset = offset, doc = doc)
        self.scale = scale
        self.scale_offset = scale_offset

    def represent(self, value):
        return super().represent(self.scale * (value + self.scale_offset))

    def parse(self, value):
        return super().parse((int(value) - self.scale_offset) // self.scale)

    def docstring(self):
        return _Field.docstring(self) + f"""
Scaled value by {self.scale} with integer offset of {self.offset} and scale offset of {self.scale_offset}
value = {self.offset} + {self.scale} * ({self.scale_offset} + field)
field = (value - {self.offset}) // {self.scale} - {self.scale_offset}
"""

class EnumField(Field):
    def __init__(self, lsb, width, enum_class, doc = None):
        super().__init__(lsb, width, doc = doc)
        self.enum_class = enum_class

    def parse(self, value):
        if isinstance(value, self.enum_class):
            return int(value)
        if isinstance(value, str):
            try:
                return int(self.enum_class[value])
            except KeyError:
                pass
        return int(value)

    def represent(self, value):
        try:
            return self.enum_class(int(value))
        except ValueError:
            return value

    def docstring(self):
        return _Field.docstring(self) + f"""
        Enumeration value from {self.enum_class}
        """

    def pretty(self, v):
        if isinstance(v, self.enum_class):
            return v.name
        return v

class MappingField(Field):
    def __init__(self, lsb, width, mapping, doc = None):
        super().__init__(lsb, width, doc = doc)
        if isinstance(mapping, dict):
            self.raw2display = {i: v for (i, v) in mapping.items()}
        else:
            self.raw2display = {i: v for (i, v) in enumerate(mapping)}
        self.display2raw = {v : k for (k, v) in self.raw2display.items()}

    def parse(self, value):
        return self.display2raw.get(value, value)

    def represent(self, value):
        return self.raw2display.get(value, value)

    def docstring(self):
        return _Field.docstring(self) + f"""
Mapping value:
""" + "\n".join([f"- {k}: {v}" for (k, v) in sorted(self.raw2display.items())])

    def pretty(self, v):
        return v

class BooleanField(Field):
    def __init__(self, bit, *, inverted = False, doc = None):
        super().__init__(bit, 1, doc = doc)
        self.inverted = bool(inverted)

    def parse(self, value):
        return int(bool(value) ^ self.inverted)

    def represent(self, value):
        return bool(value) ^ self.inverted

    def docstring(self):
        return _Field.docstring(self) + f"""
Boolean field""" + (", inverted" if self.inverted else "")

class BinaryField(MappingField):
    def __init__(self, bit, when0, when1, doc = None):
        super().__init__(bit, 1, {0: when0, 1: when1}, doc = doc)

class GrayField(Field):
    def parse(self, value):
        return value ^ (value >> 1)

    def represent(self, value):
        mask = value >> 1
        while mask:
            value ^= mask
            mask >>= 1
        return value

class _register_meta(type):
    def __new__(cls, name, bases, attrs, **kwargs):
        new_attrs = {}
        fields = {}

        attrs = dict(attrs)

        for b in bases:
            try:
                fs = b._fields
            except AttributeError:
                continue
            fields.update(fs)

        if "fields" in attrs:
            fields.update(attrs.pop("fields"))

        for item_name, item in attrs.items():
            if isinstance(item, Field):
                fields[item_name] = item
            else:
                new_attrs[item_name] = item

        lsb = min((field.lsb for field in fields.values()), default = 0)
        msb = max((field.msb for field in fields.values()), default = 0)

        if "all" in fields:
            lsb = min(fields["all"].lsb, lsb)
            msb = max(fields["all"].msb, msb)

        width = msb - lsb + 1
        fields["all"] = Field(lsb, width, doc = "Automatic field that covers the whole bitfield")
        
        new_attrs["_lsb"] = lsb
        new_attrs["_width"] = width
        new_attrs["_fields"] = fields
        new_attrs["__slots__"] = list(fields.keys()) + ["__value"]
        new_attrs["__doc__"] = (attrs.get("__doc__", "") or "") + f"""
{width}-bit bitfield with {len(fields)} fields.
"""
            
        new_class = type.__new__(cls, name, bases, new_attrs, **kwargs)

        for field_name, field in fields.items():
            setattr(new_class, field_name, property(
                fget = field.get_from,
                fset = field.set_to,
                doc = field.docstring(),
            ))

        return new_class

class Bitfield(object, metaclass = _register_meta):
    def __init__(self, *args, **kwargs):
        self.__value = 0

        if args and len(args) != 1:
            raise ValueError("Cannot specify more than one init value")
        if args and kwargs:
            raise ValueError("Cannot specify both global and fields values")

        if args:
            self.all = args[0]

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __int__(self):
        return self.__value

    def dump_pretty(self, printer):
        widest = max([v.width for (n, v) in self._fields.items() if n != "all"], default = 1)
        msb = max([1] + [v.msb+1 for v in self._fields.values()])
        nibble_count = (msb + 3) // 4
        val_nibble_count = (widest + 3) // 4
        val_fmt = "%%0%dx" % val_nibble_count

        def sorter_key(kv):
            k, v = kv
            return k != "all", v.lsb, -v.width

        printer(self.__class__.__name__)
        printer(self.__doc__)

        for name, f in sorted(self._fields.items(), key = sorter_key):
            aligned_post_nibbles = f.lsb // 4
            aligned_pre_nibbles = nibble_count - (f.msb + 4) // 4
            aligned_nibbles = nibble_count - aligned_pre_nibbles - aligned_post_nibbles

            aligned_pad_post = " " * (aligned_post_nibbles)
            aligned_pad_pre = " " * (aligned_pre_nibbles)

            aligned_fmt = "%%0%dx" % (aligned_nibbles)
            aligned_val = aligned_fmt % (self[f.slice] << (f.lsb % 4))
            aligned_mask = aligned_fmt % (((1 << f.width) - 1) << (f.lsb % 4))
            val = val_fmt % self[f.slice]

            if name == "all":
                printer("                               %s %s" % (aligned_mask, aligned_val))
                continue
            
            if f.doc:
                printer("                               %s %s %s %s" % (
                    " " * nibble_count,
                    " " * nibble_count,
                    " " * val_nibble_count,
                    f.doc))
            printer(" [%2d:%2d]  % -20s %s%s%s %s%s%s %s %s" % (
                f.msb, f.lsb, name,
                aligned_pad_pre, aligned_mask, aligned_pad_post,
                aligned_pad_pre, aligned_val, aligned_pad_post,
                val, f.get_from(self)))

    def __str__(self):
        values = {
            name: f.pretty(f.get_from(self))
            for name, f in self._fields.items()
            if name != "all"
        }
        fields = ", ".join(f"{name} = {value}" for name, value in sorted(values.items()))
        return f"<{self.__class__.__name__}: {fields}>"

    def __repr__(self):
        values = {
            name: f.pretty(f.get_from(self))
            for name, f in self._fields.items()
            if name != "all"
        }
        fields = ", ".join(f"{name} = {value}" for name, value in sorted(values.items()))
        return f"{self.__class__.__name__}({fields})"

    def set(self, value):
        self.__value = int(value)

    def __getitem__(self, r):
        if isinstance(r, int):
            return (self.__value >> r) & 1
        if isinstance(r, slice):
            return (self.__value >> r.start) & ((1 << (r.stop - r.start)) - 1)
        raise ValueError(r)

    def __setitem__(self, r, v):
        if isinstance(r, int):
            self.__value = (self.__value & ~(1 << r)) | (int(bool(v)) << r)
            return

        if isinstance(r, slice):
            mask = (((1 << (r.stop - r.start)) - 1) << r.start)
            masked_out = self.__value & ~mask
            shifted = int(v) << r.start
            self.__value = masked_out | (shifted & mask)
            return

        raise ValueError(r)
        
def _main():
    class SomeReg(Bitfield):
        a = Field(0, 4)
        b = Field(4, 4)
        c = BooleanField(4)
        d = Log2Field(4, 3, log_offset = 2, offset = 8)
        
    r = SomeReg(0x23)
    print(r.a)
    print(r.b)
    print(r.all)
    r.a = 0x7
    print(r.a)
    print(r.b)
    print(r.all)
    r.b = 0x8
    print(r.a)
    print(r.b)
    print(r.all)
    return SomeReg

if __name__ == "__main__":
    _main()
