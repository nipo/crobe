from . import model

@model.Program.ext_db.register("bin")
@model.Program.format_db.register("bin")
class BinaryProgram(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        if filename.endswith(".bin.gz"):
            import gzip
            fd = gzip.open(filename, 'rb')
        else:
            fd = open(filename, 'rb')
        self.append(model.Segment(offset, fd.read(), filename))

@model.Program.format_db.register("raw")
class RawProgram(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        fd = open(filename, 'rb')
        self.append(model.Segment(offset, fd.read(), filename))
