from . import model

@model.Program.ext_db.register("mem")
@model.Program.format_db.register("mem")
class MemProgram(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        with open(filename, "r") as fd:
            address = None
            data = b''
            for line in fd.readlines():
                line = line.strip()
                if line.startswith("/"):
                    continue
                if line.startswith("@"):
                    if address is not None and data:
                        self.append(model.Segment(address + offset, data))
                    data = b''
                    address = int(line[1:], 16)
                    continue
                data += bytes([int(line, 16)])
            if address is not None and data:
                self.append(model.Segment(address + offset, data))
