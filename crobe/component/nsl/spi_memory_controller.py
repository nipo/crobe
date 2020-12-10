from ...model import PortComponent
from ...protocol import spi
import enum

class SpiMemoryController(PortComponent):
    def __init__(self, port, name = "SpiMemoryController"):
        super().__init__(port, name)
        self.write_opcode = 0xf8
        self.read_opcode = 0
        self.addr_size = 1

    def mem_read(self, addr, size):
        addr = int(addr).to_bytes(self.addr_size, "big")
        read_command = bytes([self.read_opcode]) + addr + bytes([0])
        cmd = self.port.cmd_shift(read_command, read_miso = False)
        data = self.port.cmd_shift(size, read_miso = True)

        self.port.execute([self.port.cmd_cs(True), cmd, data, self.port.cmd_cs(False)])
        return data.miso

    def mem_write(self, addr, data):
        addr = int(addr).to_bytes(self.addr_size, "big")
        read_command = bytes([self.write_opcode]) + addr
        cmd = self.port.cmd_shift(read_command + data, read_miso = False)
        padding = self.port.cmd_shift(b'\x00', read_miso = False)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False), padding])
