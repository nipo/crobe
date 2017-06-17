__all__ = ['Segment', 'Program']

__doc__ = """Program memory"""

class Segment:
    """A blob with a base address"""

    def __init__(self, address = 0, data = ""):
        self.data = data
        self.address = address

    def __getslice__(self, begin, end):
        return self.data[begin:end]

    def __setslice__(self, begin, end, data):
        assert len(data) == end - begin
        self.data = self.data[:begin] + data + self.data[end:]

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

    def indexof(self, blob):
        return self.data.index(blob)

class Program:
    """Program memory contents"""
    def __init__(self):
        self.segments = []

    def append(self, seg):
        self.segments.append(seg)

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
        return min([s.address for s in self.segments], 0)

    @property
    def end(self):
        return max([s.end for s in self.segments], 0)

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

    def pprint(self):
        print("Program:")
        for s in sorted(self.segments):
            print(" - 0x%08x:0x%08x (%d bytes)" % (s.address, s.end, len(s)))

    def simplified(self, page_size = 1024, fill = "\xff"):
        ret = self.__class__()

        last = None
        for cur in sorted(self.segments):
            if last and last.end + page_size >= cur.address:
                padding = fill * (cur.address - last.end)
                ret.segments.pop()
                last = Segment(last.address, last.data + padding + cur.data)
            else:
                last = cur

            ret.segments.append(last)

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

            for secno in range(elf.num_segments()):
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
        
        self = cls()

        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header = fd.read(len(HEADER))
        if header != HEADER:
            raise ValueError("Bad header in %s" % filename)
        
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
                return self

            size, = struct.unpack(">H", fd.read(2))
            blob = fd.read(size)
            if len(blob) != size:
                raise ValueError("Short payload in %s" % filename, len(blob), size)
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

if __name__ == "__main__":
    import sys
    
    Program.from_file(sys.argv[1]).pprint()
