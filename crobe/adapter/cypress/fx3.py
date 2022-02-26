from .. import model
import binascii
import time
from . import fx

__all__ = ["Adapter"]

class Adapter(fx.Adapter):
    def is_in_bootloader(self):
        ret = self.ctrl_in(0xf3, index = 0, value = 0, length = 1)
        self.logger.debug("Bootloader mode: %s", ret)
        return ret[0] == 1

    def reenumerate(self):
        try:
            self.ctrl_out(0xf2, index = 0, value = 0)
        except:
            self.logger.error("Reenumeration failed")
        time.sleep(.6)

    def jump_to(self, address):
        self.mem_write(address, b'')

    def firmware_load(self, program):
        self.logger.trace("Loading %s", program)
#        self.jump_to(0)

        fx.Adapter.firmware_load(self, program)

        entry = program.info["entry"]

        self.logger.debug("Setting entry point: 0x%08x" % entry)
        self.jump_to(entry)

        time.sleep(.6)
