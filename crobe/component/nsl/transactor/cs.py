from ....model import PortComponent
from ....protocol import base, chipcon

class ControlStatus(PortComponent):
    CMD_WRITE        = 0
    CMD_READ         = 0x80

    def __init__(self, route):
        super().__init__(route, "cs")

    def reg_read(self, no):
        rsp = self.port.execute(bytes([self.CMD_READ | no]), 5)
        return int.from_bytes(rsp[1:5], 'little')

    def reg_write(self, no, value):
        self.port.execute(bytes([self.CMD_WRITE | no]) + value.to_bytes(4, "little"), 1)
