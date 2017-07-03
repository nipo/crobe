__all__ = ['Segment', 'Program']

__doc__ = """Program memory"""

class Segment:
    """A blob with a base address"""

    def __init__(self, address = 0, data = b""):
        self.data = data
        self.address = address

    def __setitem__(self, index, data):
        if isinstance(index, slice):
            assert len(data) == index.stop - index.start
            self.data = self.data[:index.start] + data + self.data[index.stop:]
        else:
            self.data = self.data[:index] + data + self.data[index + 1:]

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
        for s in self.segments:
            out(" - %s" % s)

    def paged(self, page_size = 1024, fill = b"\xff"):
        ret = self.__class__()

        for s in self.segments:
            aligned_address = s.address & ~(page_size - 1)
            end = s.address + len(s)
            aligned_end = ((end | (page_size - 1)) + 1) if (end & (page_size - 1)) else end
            
            for page_addr in range(aligned_address, aligned_end, page_size):
                t = ret.segment_at(page_addr)
                if not t:
                    t = Segment(page_addr, fill * page_size)
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
                self.info["build_date"] = datetime.datetime.strptime(date, "%Y/%m/%d %H:%M:%S")
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

    @classmethod
    def from_file(cls, filename, offset = 0):
        """Load a Program from a file"""
        from os.path import splitext
        from elftools.common.exceptions import ELFError

        if filename.endswith(".bin"):
            return cls.from_bin(filename, offset)
        if filename.endswith(".bit") or filename.endswith(".bit.gz"):
            return cls.from_bit(filename, offset)
        if filename.endswith(".hex") or filename.endswith(".ihex"):
            return cls.from_ihex(filename, offset)
        try:
            return cls.from_elf(filename, offset)
        except ELFError:
            pass
        raise RuntimeError("Format of %s not .bin, .hex or ELF" % filename)

    def save(self, filename):
        if filename.endswith(".bin"):
            return self.save_bin(filename)
        if filename.endswith(".hex"):
            return self.save_hex(filename)
        raise ValueError("Cannot guess file format")

    def save_bin(self, filename):
        fd = open(filename, "wb")

        begin = self.address
        end = self.end

        blob = b'\x00' * (end - begin)
        for s in self.segments:
            blob = blob[: s.address - begin] + s.data + blob[s.address - begin + len(s):]

        fd.write(blob)
        fd.close()

    def save_hex(self, filename):
        from .ihex import IHex

        f = IHex()

        for s in self.segments:
            f.insert_data(s.address, s.data)

        f.write_file(filename)

if __name__ == "__main__":
    import sys
    
    Program.from_file(sys.argv[1]).pprint()
