import struct
from ...db import Db

class Core:
    db = Db("Datatype")

    def __init__(self, accessor, pointer, type, tag):
        self.accessor = accessor
        self.pointer = pointer
        self.type, self.tag = type, tag

    @classmethod
    def parse(cls, accessor, pointer):
        type, tag = struct.unpack("<H2s", accessor.read(pointer, 4))
        return cls.db.call((tag, type), accessor, pointer, type, tag)
        
    def __str__(self):
        return f"<{self.tag}/{self.type}>"

Core.db.register_default(Core)

_names = {
    (b'RP', 0x02031c86): ("program_name","Program name",),
    (b'RP', 0x11a9bc3a): ("program_version_string","Program version string",),
    (b'RP', 0x9da22254): ("program_build_date_string","Program build date string",),
    (b'RP', 0x68f465de): ("binary_end","Binary end",),
    (b'RP', 0x1856239a): ("program_url","Program URL",),
    (b'RP', 0xb6a07c19): ("program_description","Program description",),
    (b'RP', 0xa1f4b453): ("program_feature","Program feature",),
    (b'RP', 0x4275f0d3): ("program_build_attribute","Program build attribute",),
    (b'RP', 0x5360b3ab): ("sdk_version","SDK version",),
    (b'RP', 0xb63cffbb): ("pico_board","Pico board",),
    (b'RP', 0x7f8882e1): ("boot2_name","Boot2 name",),
    (b'MP', 0x4a99d719): ("frozen","Frozen",),
}

@Core.db.register((b'RP', 1))
class RawData(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)

    def __str__(self):
        return f"<{self.tag} Raw data>"

@Core.db.register((b'RP', 2))
class SizedData(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        self.size = accessor.read(pointer+4, 4)
        self.data = accessor.read(pointer+8, self.size)

    def __str__(self):
        return f"<{self.tag} Data: {self.data.hex()}>"

@Core.db.register((b'RP', 3))
class ListZeroTerminated(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        # TODO

    def __str__(self):
        return f"<{self.tag} ListZeroTerminated>"

@Core.db.register((b'RP', 4))
class Bson(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        # TODO

    def __str__(self):
        return f"<{self.tag} Bson>"

@Core.db.register((b'RP', 5))
class IdAndInt(Core):
    NAMES = _names

    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        self.id, self.value = struct.unpack("<LL", accessor.read(pointer+4, 8))
        self.key, self.pretty_name = self.NAMES.get((self.tag, self.id), (f'{self.id:#010x}', f'Unknown ID {self.id:#010x}'))

    def __str__(self):
        return f"<{self.tag} Int {self.pretty_name}: {self.value:#010x}>"

@Core.db.register((b'MP', 6))
@Core.db.register((b'RP', 6))
class IdAndString(Core):
    NAMES = _names

    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        self.id, strp = struct.unpack("<LL", accessor.read(pointer+4, 8))
        self.value = b''
        while not b'\x00' in self.value:
            self.value += accessor.read(strp+len(self.value), 32)
        self.value = str(self.value.split(b'\x00')[0], 'utf-8')
        self.key, self.pretty_name = self.NAMES.get((self.tag, self.id), (f'{self.id:#010x}', f'Unknown ID {self.id:#010x}'))

    def __str__(self):
        return f"<{self.tag} Str {self.pretty_name}: '{self.value}'>"

@Core.db.register((b'MP', 7))
@Core.db.register((b'RP', 7))
class BlockDevice(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)

    def __str__(self):
        return f"<{self.tag} Block Device>"

@Core.db.register((b'RP', 8))
class PinsWithFunc(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)
        encoding = int.from_bytes(accessor.read(pointer + 4, 4), "little")
        func = (encoding >> 3) & 0xf
        if encoding & 0x7 == 2:
            pins = set([((encoding >> (7 + i * 5)) & 0x1f) for i in range(5)])
        elif encoding & 0x7 == 1:
            lo, hi = [((encoding >> (7 + i * 5)) & 0x1f) for i in range(2)]
            pins = set(range(lo, hi+1))
        else:
            pins = set()
        self.func = func
        self.pins = pins

    def __str__(self):
        return f"<{self.tag} Pins {self.pins}, func {self.func}>"

@Core.db.register((b'RP', 9))
class PinsWithNames(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)

    def __str__(self):
        return f"<{self.tag} Pins with names>"

@Core.db.register((b'RP', 10))
class NamedGroup(Core):
    def __init__(self, accessor, pointer, type, tag):
        super().__init__(accessor, pointer, type, tag)

    def __str__(self):
        return f"<{self.tag} Named group>"

class Accessor:
    def read(self, address, size):
        ...
    
class LoadableAccessor(Accessor):
    def __init__(self, program):
        self.program = program.simplified()

    def read(self, address, size):
        return self.program.read(address, size)

class BusAccessor(Accessor):
    def __init__(self, bus, offset = 0x10000000):
        self.bus = bus
        self.offset = offset

    def read(self, address, size):
        return self.bus.read(address - self.offset, size)

class Marker:
    MARKER_START = (0x7188ebf2).to_bytes(4, "little")
    MARKER_END = (0xe71aa390).to_bytes(4, "little")

    def __init__(self, backend):
        from ..model import Program
        from ...component.model import Bus
        if isinstance(backend, Program):
            accessor = LoadableAccessor(backend)
        elif isinstance(backend, Bus):
            accessor = BusAccessor(backend)
        else:
            raise ValueError(f"Unsupported backend {backend}")

        header = accessor.read(0x10000000, 512)
        start_index = header.index(self.MARKER_START)
        end_index = header.index(self.MARKER_END, start_index)
        if end_index - start_index != 16:
            raise ValueError("Bad binary info marker size")

        self.start, self.end, self.mapping = struct.unpack("<LLL", header[start_index+4:end_index])
        self.accessor = accessor

    def __iter__(self):
        for point in range(self.start, self.end, 4):
            ptr = int.from_bytes(self.accessor.read(point, 4), "little")
            yield Core.parse(self.accessor, ptr)
