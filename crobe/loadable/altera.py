from . import model
import struct
import datetime

@model.Program.ext_db.register("pof")
@model.Program.ext_db.register("pof.gz")
class PofBitstream(model.Program):
    HEADER = b"POF\x00"

    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        if hasattr(filename, "read"):
            fd = filename
        elif filename.endswith(".pof.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header = fd.read(len(self.HEADER))
        if header != self.HEADER:
            raise ValueError("Bad header in %s" % filename)
        info = {}

        raise NotImplementedError()


@model.Program.ext_db.register("sof")
@model.Program.ext_db.register("sof.gz")
class SofBitstream(model.Program):
    HEADER = b"SOF\x00"

    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        if hasattr(filename, "read"):
            fd = filename
        elif filename.endswith(".sof.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')

        header = fd.read(len(self.HEADER))
        if header != self.HEADER:
            raise ValueError("Bad header in %s" % filename)

        _, count = struct.unpack("<LL", fd.read(8))

        info = {}

        raise NotImplementedError()
