from ...model import PortComponent
from ...protocol import spi
import time

@spi.Target.db.register("tc72")
class Tc72(PortComponent):
    def __init__(self, port):
        super().__init__(port, "tc72")
        self.port.freq_cap("tc72", 7.5e6)

    def _read(self, base, length):
        cmd = self.port.cmd_shift(bytes([int(base)]), read_miso = False)
        cmd2 = self.port.cmd_shift(b'\x00' * length, read_miso = True)
        self.port.execute([self.port.cmd_cs(True), cmd, cmd2, self.port.cmd_cs(False)])
        return cmd2.miso

    def _write(self, base, data):
        cmd = self.port.cmd_shift(bytes([0x80 | int(base)]) + data, read_miso = False)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])

    def control_set(self, one_shot = False, shutdown = True):
        v = 0x04
        v |= 0x10 if one_shot else 0
        v |= 0x01 if shutdown else 0
        self._write(0, bytes([v]))

    def control_get(self):
        return self._read(0, 1)[0]

    def id_get(self):
        return self._read(3, 1)[0]

    def is_conversion_ready(self):
        ctrl = self.control_get()
        return (ctrl & 1) == 0 or (ctrl & 0x10) == 0

    def temperature_get(self):
        """Temperature reading in Celcius"""
        value = int.from_bytes(self._read(1, 2), "little", signed = True)
        return value / 256.

    def temperature_measure(self):
        """Trigger one-shot, wait for completion and return reading in Celcius"""
        self.control_set(shutdown = False)
#        while not self.is_conversion_ready():
        time.sleep(.01)
        return self.temperature_get()

    def sensors_read(self):
        self.control_set(one_shot = True)
        while not self.is_conversion_ready():
            time.sleep(.01)
        return dict(T = self.temperature_get() + 273.15)
