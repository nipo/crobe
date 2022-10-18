from . import model
import struct

@model.Program.ext_db.register("dfu")
@model.Program.format_db.register("dfu")
class DfuProgram(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        with open(filename, 'rb') as fd:
            blob = fd.read()
            from zlib import crc32

            c = crc32(blob) ^ 0xffffffff
            suffix_length = blob[-4]
            
            if c != 0 or blob[-8:-5] != b"UFD" or suffix_length < 0x10:
                raise ValueError("Bad file contents")

            trailer = blob[-suffix_length:-8]
            blob = blob[:-suffix_length]

            self.append(model.Segment(0, blob, self))
            device, pid, vid, version = struct.unpack("<HHHH", trailer[-8:])

            self.info["idVendor"] = vid
            self.info["idProduct"] = pid
            self.info["bcdDevice"] = device
            self.info["bcdDfu"] = version
