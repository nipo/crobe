from .. import model
import binascii
import time
from . import fx

__all__ = ["Adapter"]

class Adapter(fx.Adapter):
    def reset(self, enable_cpu):
        cpu_address = 0xE600
        data = bytes([int(bool(enable_cpu))])
        self.mem_write(cpu_address, data)

    def firmware_load(self, program):
        try:
            self.device.set_configuration(0)
        except:
            pass
        self.reset(True)

        fx.Adapter.firmware_load(self, program)

        self.reset(False)
