from . import model
import struct

@model.Program.ext_db.register("img")
@model.Program.ext_db.register("img.gz")
@model.Program.format_db.register("img")
class Fx2Image(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        if filename.endswith(".img.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header, ctl, typ = struct.unpack("2sBB", fd.read(4))
        if header != b"CY":
            raise ValueError("Bad file header")

        chk = 0

        while True:
            ch = fd.read(8)
            size, address = struct.unpack("<LL", ch)
            if size == 0:
                break
            blob = fd.read(size * 4)
            self.append(model.Segment(address + offset, blob, filename))
            chk += sum(struct.unpack("<%dL" % (len(blob) // 4), blob))

        checksum, = struct.unpack("<L", fd.read(4))

        if checksum != chk & 0xffffffff:
            raise ValueError("Bad file checksum")

        self.info["entry"] = address
        self.info["checksum"] = checksum
        self.info["flash_config"] = ctl
        self.info["type"] = typ
