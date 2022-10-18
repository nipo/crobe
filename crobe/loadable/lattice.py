from . import model
import struct
import datetime
from ..util.endian import bitswap8
import warnings

@model.Program.ext_db.register("bit")
@model.Program.ext_db.register("bit.gz")
@model.Program.format_db.register("bit")
class LatticeBitstream(model.Program):
    HEADER = b"\xff\x00Lattice Semiconductor Corporation Bitstream\x00"
    HEADER_END = b"\x00\xff"
    START = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])

    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        
        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        blob = fd.read()
        fd.close()

        has_header = blob.startswith(self.HEADER)
        start = blob.find(self.START)
        
        if start < 0:
            start = blob.index(bitswap8(self.START))

            if 0 <= start < 1024:
                blob = bitswap8(blob)

        if start > 1024:
            raise ValueError("Start too far from file begin")

        if has_header:
            header_end = blob.index(self.HEADER_END)

            for f in str(blob[len(self.HEADER) : header_end], "ascii").split("\x00"):
                k, v = f.split(": ", 1)
                self.info[k] = v
            if start != header_end + 2:
                warnings.warn("Something present between header and start of bitstream ??")
                
        else:
            warnings.warn("Would prefer Lattice bitstream with ASCII header")

        self.append(model.Segment(offset, blob[start:], filename))
