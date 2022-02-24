from ...model import PortComponent
from ..model import SramFpga
from ...protocol import spi
import time

__all__ = ["Ice40SlaveSerial"]

@spi.Target.db.register("ice40_slave")
def ice40_slave_probe(target, *args):
    return Ice40SlaveSerial(target)

class Ice40SlaveSerial(PortComponent, SramFpga):
    def __init__(self, port):
        PortComponent.__init__(self, port, "Slave iCE40")
        SramFpga.__init__(self)

    def start(self):
        self.port.freq_cap("iCE40", 15e6)
        super().start()

    def stop(self):
        pass

    def reset(self):
        self.port.port.reset = True
        self.port.port.reset = False

    def load(self, program):
        self.port.port.reset = True
        self.port.execute([self.port.cmd_cs(True), self.port.cmd_shift(b'\xb9', read_miso = False)])
        self.port.port.reset = False
        self.port.execute([self.port.cmd_shift(b'\x00'*32, read_miso = False)])

        self.port.execute([self.port.cmd_shift(b'\x00'*32, read_miso = False)])
        blob = program.simplified().segment_at(0).data
        self.logger.trace("Loading %d bytes bitstream", len(blob))
        for off in range(0, len(blob), 1024):
            chunk = blob[off : off + 1024]
            self.port.execute([self.port.cmd_shift(chunk, read_miso = False)])
        self.port.execute([self.port.cmd_cs(False)])
        self.port.execute([self.port.cmd_shift(b'\x00'*32, read_miso = False)])
