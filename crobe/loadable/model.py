from .. import db

__all__ = ['Segment', 'Program']

__doc__ = """Program memory"""

class Segment:
    """A blob with a base address"""

    def __init__(self, address = 0, data = b"", source = None, name = None):
        self.data = bytearray(data)
        self.address = address
        self.source = source
        self.name = name

    def __setitem__(self, index, data):
        self.data[index] = data

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    @property
    def end(self):
        return self.address + len(self.data)

    def __lt__(self, other):
        return self.address < other.address

    def __eq__(self, other):
        return self.address == other.address

    def __lte__(self, other):
        return self.address <= other.address

    def __str__(self):
        return "<0x%08x:0x%08x (%d bytes)%s>" % (self.address, self.end, len(self),
                                                 (" '%s'" % self.name) if self.name else "")
    
    def indexof(self, blob):
        return self.data.index(blob)
    
class Program:
    """Program memory contents"""

    ext_db = db.Db("Extension")
    format_db = db.Db("Format")
    
    def __init__(self, filename = None):
        self.segments = []
        self.sources = []
        if filename:
            self.sources.append(filename)
        self.info = {}

    def append(self, seg):
        assert isinstance(seg, Segment)
        self.segments.append(seg)

    def segment_at(self, addr):
        for s in self.segments:
            if s.address <= addr < s.address + len(s):
                return s

    def within(self, begin, end):
        ret = Program()
        for s in self.segments:
            left = max(begin, s.address)
            right = min(s.address + len(s), end)
            #print(hex(begin), hex(end), hex(left), hex(right), hex(left-s.address), hex(right-s.address))
            if left > right:
                continue
            ret.append(Segment(left, s[left-s.address : right-s.address], s.source))
        return ret

    def read(self, address, size):
        ret = bytearray(b"\x00" * size)
        for s in self.segments:
            left = max(address, s.address)
            right = min(s.address + len(s), address + size)
            if left > right:
                continue
            ret[left-address : right-address] = s[left-s.address : right-s.address]
        return ret
    
    def __getitem__(self, index):
        return self.segments[index]

    def __len__(self):
        return len(self.segments)

    def __iter__(self):
        return iter(self.segments)

    def indexof(self, blob):
        for s in self.segments:
            try:
                return s.indexof(blob) + s.address
            except ValueError:
                pass
        raise ValueError("Not found")
    
    @property
    def size(self):
        return sum([len(s) for s in self.segments], 0)
    
    @property
    def address(self):
        return min([s.address for s in self.segments], default = 0)

    @property
    def end(self):
        return max([s.end for s in self.segments], default = 0)

    def __add__(self, other):
        ret = Program()
        for s in self:
            ret.append(s)
        ret += other
        return ret

    def __iadd__(self, other):
        for s in other:
            self.append(s)
        for source in other.sources:
            self.sources.append(source)
        return self

    def pprint(self, out = print):
        out(f"{self.__class__.__name__}:")
        for k, v in sorted(self.info.items()):
            if isinstance(v, int):
                out(" + %s: 0x%x (%d)" % (k, v, v))
            else:
                out(" + %s: %s" % (k, v))
        for s in self.segments:
            out(" - %s" % s)

    def paged(self, page_size = 1024, fill = b"\xff"):
        ret = Program()
        page_fill = fill * page_size

        for s in self.segments:
            aligned_address = s.address & ~(page_size - 1)
            end = s.address + len(s)
            aligned_end = ((end | (page_size - 1)) + 1) if (end & (page_size - 1)) else end

            for page_addr in range(aligned_address, aligned_end, page_size):
                t = ret.segment_at(page_addr)
                if not t:
                    t = Segment(page_addr, page_fill, s.source)
                    ret.append(t)
                source_offset = max((page_addr - s.address, 0))
                target_offset = (s.address & (page_size - 1)) if page_addr == aligned_address else 0
                size = min((len(s) - source_offset, page_size - target_offset, page_size))
                t[target_offset : target_offset + size] = s[source_offset : source_offset + size]

        return ret

    def simplified(self):
        ret = Program()
        addr = data = None

        for s in sorted(self.segments, key = lambda x: x.address):
            if data:
                if s.address == addr + len(data):
                    data += s.data
                    continue
                if s.address < addr + len(data):
                    if s.address + len(s) < addr + len(data):
                        data = data[: s.address - addr] + s.data + data[s.address - addr + len(s) :]
                    else:
                        data = data[: s.address - addr] + s.data
                    continue
                ret.append(Segment(addr, data, s.source))
                addr = data = None
            addr = s.address
            data = s.data

        if data:
            ret.append(Segment(addr, data, s.source))
        ret.info.update(self.info)

        return ret

    def save(self, filename):
        if filename.endswith(".bin"):
            return self.save_bin(filename)
        if filename.endswith(".hex"):
            return self.save_hex(filename)
        raise ValueError("Cannot guess file format")

    def save_bin(self, filename):
        fd = open(filename, "wb")
        self.bin_dump(fd)
        fd.close()

    def save_cypress_img(self, filename, type = 0xb0):
        fd = open(filename, "wb")

        fd.write(b"CY")
        fd.write(bytes([self.info.get("flash_config", 0x20), 0xb0]))

        chk = 0

        for s in self.segments:
            for off in range(0, len(s), 4096):
                blob = s.data[off:off+4096]
                if len(blob) % 4:
                    blob += b"\x00" * (-len(blob) % 4)
                fd.write(struct.pack("<LL", len(blob) // 4, s.address + off))
                fd.write(blob)
                chk += sum(struct.unpack("<%dL" % (len(blob) // 4), blob))
        fd.write(struct.pack("<LL", 0, self.info["entry"]))
        fd.write(struct.pack("<L", chk & 0xffffffff))
        fd.close()

    def bin_dump(self, fd, bitswap = False):
        begin = self.address
        end = self.end

        blob = b'\x00' * (end - begin)
        for s in self.segments:
            blob = blob[: s.address - begin] + s.data + blob[s.address - begin + len(s):]

        if bitswap:
            from ..util.endian import bitswap8
            blob = bitswap8(blob)
        fd.write(blob)

    def save_hex(self, filename):
        from .ihex import IHex

        f = IHex()
        f.set_mode(32)

        for s in self.segments:
            f.insert_data(s.address, s.data)

        f.write_file(filename)

    @classmethod
    def from_file(cls, filename, offset = 0):
        """Load a Program from a file"""
        from os.path import splitext

        parsers = []

        while ':' in filename:
            try:
                pos = filename.rindex(":", 2)
            except ValueError:
                break

            option = filename[pos+1:]
            filename = filename[:pos]
            
            if option.startswith("+"):
                offset += int(option[1:], 16)
                continue

            try:
                parsers = cls.format_db.get(option.lower())
                continue
            except db.NoMatch:
                pass
            raise ValueError(f"Bad option: {option}")

        parts = filename.split(".")
        for i in range(1, 3):
            ext = '.'.join(parts[-i:])

            try:
                parsers += cls.ext_db.get(ext)
            except db.NoMatch:
                pass
            
        for p in parsers:
            try:
                return p(filename, offset)
            except db.NoMatch:
                pass
            except ValueError:
                raise
            except Exception as e:
                warnings.warn(f"Loading {filename} with {p} failed: {e}")
                pass

        raise RuntimeError(f"Format of {filename} not known")

    @classmethod
    def from_files(cls, filenames):
        return cls.from_programs([cls.from_file(f) for f in filenames])

    @classmethod
    def from_programs(cls, programs):
        if not programs:
            return None

        if len(programs) == 1:
            return programs[0]

        program = cls()

        for p in programs:
            program += p

        return program
