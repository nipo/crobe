from ...model import PortComponent
from ...protocol import spi
import enum

@spi.Target.db.register("dac3171")
class Dac3171(PortComponent):
    def __init__(self, port):
        super().__init__(port, "dac3171")
        self.four_wire_spi = True

    def option_set(self, opt):
        if opt == "spi3":
            self.four_wire_spi = False
            return
        super().option_set(opt)

    def reg_read(self, reg):
        cmd = self.port.cmd_shift(bytes([0x80 | int(reg)]), read_miso = False)
        data = self.port.cmd_shift(b"\x00" * 2, read_miso = True)

        self.port.execute([
            self.port.cmd_cs(True), cmd, data, self.port.cmd_cs(False),
        ])

        value = int.from_bytes(data.miso, "big")

        self.logger.trace("Read reg %d: 0x%04x", int(reg), int(value))

        return value

    def reg_write(self, reg, value):
        if int(reg) == 0:
            if self.four_wire_spi:
                value = int(value) | 0x200
            else:
                value = int(value) & ~0x200

        blob = int(value).to_bytes(2, "big")

        cmd = self.port.cmd_shift(bytes([int(reg)]) + blob, read_miso = False)

        self.logger.trace("Write reg %d: 0x%04x", int(reg), int(value))
        
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])
        
    def start(self):
        # Will enable sif4 if needed
        self.reg_write(0, 0x44fc)

        die_id = 0
        for i in range(0x19, 0x15, -1):
            die_id <<= 16
            die_id |= self.reg_read(i)

        self.die_id = die_id
        self.logger.note("Dac3171, Die ID: 0x%16x", die_id)
