from . import model
import struct
import datetime

@model.Program.ext_db.register("bit")
@model.Program.ext_db.register("bit.gz")
@model.Program.format_db.register("bit")
@model.Program.format_db.register("xilinx")
class XilinxBitstream(model.Program):
    HEADER = bytes([0x00, 0x09, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x0f, 0xf0, 0x00, 0x00, 0x01])

    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        if filename.endswith(".bit.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header = fd.read(len(self.HEADER))
        if header != self.HEADER:
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
            
                self.append(model.Segment(offset, blob, filename))

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
                
                return

            size, = struct.unpack(">H", fd.read(2))
            blob = fd.read(size)
            if len(blob) != size:
                raise ValueError("Short payload in %s" % filename, len(blob), size)

            info[section] = str(blob.rstrip(b'\x00'), 'utf-8', 'ignore')

        raise ValueError("Not bitstream data in %s" % filename)
