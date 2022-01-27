import warnings
from collections import deque
import struct

__all__ = ['Segment', 'Program']

__doc__ = """Program memory"""

class Segment:
    """A blob with a base address"""

    def __init__(self, address = 0, data = b"", source = None):
        self.data = bytearray(data)
        self.address = address
        self.source = source

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
        return "<0x%08x:0x%08x (%d bytes)>" % (self.address, self.end, len(self))
    
    def indexof(self, blob):
        return self.data.index(blob)
    
class Program:
    """Program memory contents"""
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
        ret = self.__class__()
        for s in self.segments:
            left = max(begin, s.address)
            right = min(s.address + len(s), end)
            #print(hex(begin), hex(end), hex(left), hex(right), hex(left-s.address), hex(right-s.address))
            if left > right:
                continue
            ret.append(Segment(left, s[left-s.address : right-s.address], s.source))
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
        ret = self.__class__()
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
        out("Program:")
        for k, v in sorted(self.info.items()):
            if isinstance(v, int):
                out(" + %s: 0x%x (%d)" % (k, v, v))
            else:
                out(" + %s: %s" % (k, v))
        for s in self.segments:
            out(" - %s" % s)

    def paged(self, page_size = 1024, fill = b"\xff"):
        ret = self.__class__()
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
        ret = self.__class__()
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

    @classmethod
    def from_ihex(cls, filename, offset = 0):
        """Load a Program from an Intel-Hex file"""
        from .ihex import IHex

        self = cls(filename)
        ih = IHex.read_file(filename)

        segment = None
        for addr, data in ih.areas.items():
            segment = Segment(addr + offset, data, filename)
            self.append(segment)
        return self

    @classmethod
    def from_cypress_img(cls, filename, offset = 0):
        """Load a Program from a Cypress FX image file"""
        if filename.endswith(".img.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header, ctl, typ = struct.unpack("2sBB", fd.read(4))
        if header != b"CY":
            raise ValueError("Bad file header")

        self = cls(filename)

        chk = 0

        while True:
            ch = fd.read(8)
            size, address = struct.unpack("<LL", ch)
            if size == 0:
                break
            blob = fd.read(size * 4)
            self.append(Segment(address + offset, blob, filename))
            chk += sum(struct.unpack("<%dL" % (len(blob) // 4), blob))

        checksum, = struct.unpack("<L", fd.read(4))

        if checksum != chk & 0xffffffff:
            raise ValueError("Bad file checksum")

        self.info["entry"] = address
        self.info["checksum"] = checksum
        self.info["flash_config"] = ctl
        self.info["type"] = typ

        return self

    @classmethod
    def from_img(cls, filename, offset = 0):
        for handler in [
            cls.from_cypress_img,
            ]:
            try:
                return handler(filename, offset)
            except ValueError:
                pass
        raise ValueError("Not a known bitstream format")

    @classmethod
    def from_elf(cls, filename, offset = 0):
        """Load a Program from an ELF file"""
        from elftools.elf.elffile import ELFFile

        self = cls(filename)
        elf = ELFFile(open(filename, "rb"))
        for segno in range(elf.num_segments()):
            seg = elf.get_segment(segno)
            if seg["p_type"] != "PT_LOAD":
                continue

            self.append(Segment(seg["p_paddr"], seg.data().ljust(seg['p_memsz'], b'\x00'), filename))

        self.info["device"] = elf.get_machine_arch()
        self.info["entry"] = elf.header["e_entry"]

        return self

    @classmethod
    def from_bin(cls, filename, offset = 0):
        """Load a Program from an Binary file"""
        self = cls(filename)
        if filename.endswith(".bin.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')
        self.append(Segment(offset, fd.read(), filename))
        return self

    @classmethod
    def from_bit(cls, filename, offset = 0):
        for handler in [
            cls.from_xilinx_bit,
            cls.from_lattice_bit,
            ]:
            try:
                return handler(filename, offset)
            except ValueError:
                pass
        raise ValueError("Not a known bitstream format")

    @classmethod
    def from_jed(cls, filename, offset = 0):
        from ..jed import jed
        j = jed.Jed(filename)

        self = cls(filename)

        self.info["fuse_count"] = j.fuse_count
        self.info["pin_count"] = j.pin_count
        self.info["device_architecture"] = j.device_architecture
        self.info["device_pinout"] = j.device_pinout
        self.info["security"] = j.security
        self.info["notes"] = '\n'.join(j.notes)
        for n in j.notes:
            if n.lower().startswith("device name: "):
                self.info["device"] = n[13:]
            elif n.lower().startswith("device "):
                self.info["device"] = n[7:]
        self.append(Segment(0, bytes(j.fuses), filename))
        return self

    @classmethod
    def from_lattice_bit(cls, filename, offset = 0):
        """Load a Program from an Lattice bit file"""
        HEADER = b"\xff\x00Lattice Semiconductor Corporation Bitstream\x00"
        HEADER_END = b"\x00\xff"
        START = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])
        import struct
        import datetime
        from ..util.endian import bitswap8
        
        self = cls(filename)

        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        blob = fd.read()
        fd.close()

        has_header = blob.startswith(HEADER)
        start = blob.find(START)
        
        if start < 0:
            start = blob.index(bitswap8(START))

            if 0 <= start < 1024:
                blob = bitswap8(blob)

        if start > 1024:
            raise ValueError("Start too far from file begin")

        if has_header:
            header_end = blob.index(HEADER_END)

            for f in str(blob[len(HEADER) : header_end], "ascii").split("\x00"):
                k, v = f.split(": ", 1)
                self.info[k] = v
            if start != header_end + 2:
                warnings.warn("Something present between header and start of bitstream ??")
                
        else:
            warnings.warn("Would prefer Lattice bitstream with ASCII header")

        self.append(Segment(offset, blob[start:], filename))
        return self

    @classmethod
    def from_fs(cls, filename, offset = 0):
        from ..bitstring import BitString

        self = cls(filename)

        with open(filename, "r") as fd:
            lines = deque(fd.readlines())
            while lines and lines[0].startswith("//"):
                try:
                    k, v = lines.popleft().strip()[2:].split(":", 1)
                except:
                    continue
                self.info[k] = v.strip()

        stream = "".join(l.strip() for l in lines)
        data = BitString(int(stream, 2), len(stream))

        self.append(Segment(0, bytes(data)[::-1], filename))

        return self

    @classmethod
    def from_xilinx_bit(cls, filename, offset = 0):
        """Load a Program from an Xilinx bit file"""
        HEADER = bytes([0x00, 0x09, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x00, 0x00, 0x01])
        import struct
        import datetime
        
        self = cls(filename)

        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header = fd.read(len(HEADER))
        if header != HEADER:
            raise ValueError("Bad header in %s" % filename)
        info = {}

        while True:
            section = fd.read(1)
            if not section:
                break
            
            if section == b'e':
                size, = struct.unpack(">L", fd.read(4))
                blob = fd.read(size)
                if len(blob) != size:
                    raise ValueError("Short payload in %s" % filename, len(blob), size)
            
                self.append(Segment(offset, blob, filename))

                date = info[b'c'].strip() + " " + info[b'd'].strip()
                try:
                    self.info["build_date"] = datetime.datetime.strptime(date, "%Y/%m/%d %H:%M:%S")
                except ValueError:
                    self.info["build_date"] = None
                self.info["device"] = info[b'b']
                parts = info[b'a'].split(';')
                self.info["project"] = parts[0]
                for p in parts[1:]:
                    k, v = p.split('=')
                    k = k.lower()
                    if k == 'userid':
                        v = int(v, 16)
                    self.info[k] = v
                
                return self

            size, = struct.unpack(">H", fd.read(2))
            blob = fd.read(size)
            if len(blob) != size:
                raise ValueError("Short payload in %s" % filename, len(blob), size)

            info[section] = str(blob.rstrip(b'\x00'), 'utf-8', 'ignore')

        raise ValueError("Not bitstream data in %s" % filename)

    EXT_MAP = {
        ".mem": "mem",
        ".jed": "jed",
        ".bin": "bin",
        ".bin.gz": "bin",
        ".bit": "bit",
        ".bit.gz": "bit",
        ".img": "img",
        ".img.gz": "img",
        ".hex": "ihex",
        ".ihex": "ihex",
        ".mcs": "ihex",
        ".elf": "elf",
        ".out": "elf",
        ".axf": "elf",
        ".fs": "fs",
        "__literal": "literal",
        "__zero": "zero",
        "__one": "one",
        "__random": "random",
        }

    @classmethod
    def from_file(cls, filename, offset = 0):
        """Load a Program from a file"""
        from os.path import splitext
        from elftools.common.exceptions import ELFError

        parser = None

        for ext, p in cls.EXT_MAP.items():
            if filename.endswith(ext):
                parser = p
                break

        while True:
            option = filename.split(":")[-1].lower()
            if option in cls.EXT_MAP.values():
                parser = option
            elif option.startswith("+"):
                offset += int(option[1:], 16)
            else:
                break
            filename = filename[:-len(option)-1]

        if parser is None:
            raise RuntimeError("Format of %s not known" % filename)

        return getattr(cls, "from_" + parser)(filename, offset)

    @classmethod
    def from_files(cls, filenames):
        return cls.from_programs([cls.from_file(f) for f in filenames])

    @classmethod
    def from_mem(cls, filename, offset = 0):
        self = cls()
        with open(filename, "r") as fd:
            address = None
            data = b''
            for line in fd.readlines():
                line = line.strip()
                if line.startswith("/"):
                    continue
                if line.startswith("@"):
                    if address is not None and data:
                        self.append(Segment(address + offset, data))
                    data = b''
                    address = int(line[1:], 16)
                    continue
                data += bytes([int(line, 16)])
            if address is not None and data:
                self.append(Segment(address + offset, data))
        return self

    @classmethod
    def from_literal(cls, hex_string, offset = 0):
        program = cls()
        program.append(Segment(address = offset, data = bytes.fromhex(hex_string)))
        return program

    @classmethod
    def from_random(cls, size, offset = 0):
        from ..util.random import random_data
        program = cls()
        program.append(Segment(address = offset, data = random_data(int(size, 0))))
        return program

    @classmethod
    def from_zero(cls, size, offset = 0):
        program = cls()
        program.append(Segment(address = offset, data = b'\x00' * int(size, 0)))
        return program

    @classmethod
    def from_one(cls, size, offset = 0):
        program = cls()
        program.append(Segment(address = offset, data = b'\xff' * int(size, 0)))
        return program

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
