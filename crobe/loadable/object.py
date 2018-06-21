import warnings
import struct

__all__ = ['Segment', 'Program']

__doc__ = """Program memory"""

class Segment:
    """A blob with a base address"""

    def __init__(self, address = 0, data = b""):
        self.data = bytearray(data)
        self.address = address

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
    def __init__(self):
        self.segments = []
        self.info = {}

    def append(self, seg):
        self.segments.append(seg)

    def segment_at(self, addr):
        for s in self.segments:
            if s.address <= addr < s.address + len(s):
                return s

    def within(self, begin, end):
        ret = self.__class__()
        for s in self.segments:
            if begin <= s.address and s.address + len(s) <= end:
                ret.append(s)
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
        return self

    def pprint(self, out = print):
        out("Program:")
        for k, v in sorted(self.info.items()):
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
                    t = Segment(page_addr, page_fill)
                    ret.append(t)
                source_offset = max((page_addr - s.address, 0))
                target_offset = (s.address & (page_size - 1)) if page_addr == aligned_address else 0
                size = min((len(s) - source_offset, page_size - target_offset, page_size))
                t[target_offset : target_offset + size] = s[source_offset : source_offset + size]

        return ret

    @classmethod
    def from_ihex(cls, filename, offset = 0):
        """Load a Program from an Intel-Hex file"""
        from .ihex import IHex

        self = cls()
        ih = IHex.read_file(filename)

        segment = None
        for addr, data in ih.areas.items():
            segment = Segment(addr + offset, data)
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

        self = cls()

        chk = 0

        while True:
            ch = fd.read(8)
            size, address = struct.unpack("<LL", ch)
            if size == 0:
                break
            blob = fd.read(size * 4)
            self.append(Segment(address + offset, blob))
            chk += sum(struct.unpack("<%dL" % (len(blob) // 4), blob))

        checksum, = struct.unpack("<L", fd.read(4))

        if checksum != chk & 0xffffffff:
            raise ValueError("Bad file checksum")

        self.info["entry"] = address
        self.info["checksum"] = checksum

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

        self = cls()
        elf = ELFFile(open(filename, "rb"))
        for segno in range(elf.num_segments()):
            seg = elf.get_segment(segno)
            if seg["p_type"] != "PT_LOAD":
                continue

            lma = seg["p_paddr"]
            vma = seg["p_vaddr"]

            for secno in range(elf.num_sections()):
                section = elf.get_section(secno)

                if not seg.section_in_segment(section):
                    continue

                if not section["sh_size"]:
                    continue

                data = section.data()
                if not data:
                    continue

                addr = section["sh_addr"]

                self.append(Segment(addr - vma + lma + offset, data))

        self.info["device"] = elf.get_machine_arch()
        self.info["entry"] = elf.header["e_entry"]

        return self

    @classmethod
    def from_bin(cls, filename, offset = 0):
        """Load a Program from an Binary file"""
        self = cls()
        fd = open(filename, 'rb')
        self.append(Segment(offset, fd.read()))
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
    def from_lattice_bit(cls, filename, offset = 0):
        """Load a Program from an Lattice bit file"""
        HEADER = b"\xff\x00Lattice Semiconductor Corporation Bitstream\x00"
        HEADER_END = b"\x00\xff"
        START = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])
        import struct
        import datetime
        
        self = cls()

        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        blob = fd.read()
        fd.close()

        has_header = blob.startswith(HEADER)
        start = blob.index(START)

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

        self.append(Segment(offset, blob[start:]))
        return self

    @classmethod
    def from_xilinx_bit(cls, filename, offset = 0):
        """Load a Program from an Xilinx bit file"""
        HEADER = bytes([0x00, 0x09, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x00, 0x00, 0x01])
        import struct
        import datetime
        
        self = cls()

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
            
                self.append(Segment(offset, blob))

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
        ".bin": "bin",
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
            if len(option) == 3 and option in cls.EXT_MAP.values():
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
        if len(filenames) == 1:
            return cls.from_file(filenames[0])

        program = Program()

        for filename in filenames:
            program += cls.from_file(filename)

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

    def bin_dump(self, fd):
        begin = self.address
        end = self.end

        blob = b'\x00' * (end - begin)
        for s in self.segments:
            blob = blob[: s.address - begin] + s.data + blob[s.address - begin + len(s):]

        fd.write(blob)

    def save_hex(self, filename):
        from .ihex import IHex

        f = IHex()
        f.set_mode(32)

        for s in self.segments:
            f.insert_data(s.address, s.data)

        f.write_file(filename)
