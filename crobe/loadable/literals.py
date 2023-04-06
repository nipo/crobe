from . import model

@model.Program.format_db.register("literal")
class LiteralProgram(model.Program):
    def __init__(self, hex_data, offset = 0):
        super().__init__()

        self.append(model.Segment(address = offset, data = bytes.fromhex(hex_data)))

@model.Program.format_db.register("random")
class RandomProgram(model.Program):
    def __init__(self, size, offset = 0):
        from ..util.random import random_data
        super().__init__()

        self.append(model.Segment(address = offset, data = random_data(int(size, 0))))

@model.Program.format_db.register("zero")
class ZeroProgram(model.Program):
    def __init__(self, size, offset = 0):
        super().__init__()
        
        self.append(model.Segment(address = offset, data = b'\x00' * int(size, 0)))

@model.Program.format_db.register("one")
class OneProgram(model.Program):
    def __init__(self, size, offset = 0):
        super().__init__()

        self.append(model.Segment(address = offset, data = b'\xff' * int(size, 0)))
