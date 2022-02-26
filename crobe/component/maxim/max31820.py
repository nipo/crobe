from ...model import PortComponent
from ...protocol import one_wire

@one_wire.Interface.db.register(0x28)
class Max31820(one_wire.Device):
    CONVERT_T = 0x44
    READ_SCRATCHPAD = 0xbe
    tCONV_12 = 750e-3

    def __init__(self, port, rom):
        super().__init__(port, rom, "MAX31820-%012x" % rom.uid)

    def start(self):
        super().start()
        
    def sensors_read(self):
        convert = self.cmd_command(self.CONVERT_T)
        read = self.cmd_command(self.READ_SCRATCHPAD, rsize = 9)
        self.execute([convert, self.cmd_wait(self.tCONV_12)])
        self.execute([read])

        self.logger.debug("Current scratchpad: %s %02x",
                         read.data.hex(), one_wire.crc8(read.data[:-1]))

        temp = int.from_bytes(read.data[:2], 'little', signed = True)
        temp /= 16
        
        return dict(T = temp + 273.15)
