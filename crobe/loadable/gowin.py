from . import model
import struct
import datetime
from collections import deque
from ..bitstring import BitString

@model.Program.ext_db.register("fs.gz")
@model.Program.ext_db.register("fs")
@model.Program.format_db.register("fs")
class GowinBitstream(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        if filename.endswith(".fs.gz"):
            import gzip
            fd = gzip.open(filename, 'r')
        else:
            fd = open(filename, 'r')

        lines = deque(fd.readlines())
        if isinstance(lines[0], bytes):
            lines = deque(str(x, "utf-8", "ignore") for x in lines)
        while lines and lines[0].startswith("//"):
            try:
                k, v = lines.popleft().strip()[2:].split(":", 1)
            except:
                continue
            self.info[k] = v.strip()

        stream = "".join(l.strip() for l in lines)
        data = BitString(int(stream, 2), len(stream))

        self.append(model.Segment(0, bytes(data)[::-1], filename))
