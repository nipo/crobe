from ...model import Target
from ...memory import Ram, Flash
from ....component.raspberrypi.rp2.picoboot import BootInterface
from ..model import SoC

class PicobootFlash(Flash):
    def __init__(self, boot_interface):
        self.interface = boot_interface
        super().__init__("flash", self.interface.XIP_BASE, 0, 4096)

    def erase(self, offset, size):
        offset = offset & ~0xfff
        size += (-size) & 0xfff
        self.interface.flash_erase(self.address + offset, size)

    def read(self, offset, size):
        return self.interface.read(self.address + offset, size)

    def write(self, offset, data):
        return self.interface.write(self.address + offset, data)

class PicobootRam(Ram):
    def __init__(self, boot_interface):
        self.interface = boot_interface
        super().__init__("flash", self.interface.SRAM_BASE,
                         self.interface.ram_size)

    def read(self, offset, size):
        return self.interface.read(self.address + offset, size)

    def write(self, offset, data):
        return self.interface.write(self.address + offset, data)

@Target.register(BootInterface)
class RP2BootloaderTarget(SoC):
    def __init__(self, boot_interface):
        super().__init__(boot_interface.device_name)
        self.interface = boot_interface
        self.ram = PicobootRam(boot_interface)
        self.flash = PicobootFlash(boot_interface)
        self.child_add(self.ram)
        self.child_add(self.flash)

    def start(self):
        super().start()
        self.logger.info("Probing flash size")
        self.attach()
        s0 = self.flash.read(0, 256)
        self.logger.info("At 0: %s", s0.hex())
        smallest = 1<<20
        for size_l2 in range(23, 16, -1):
            size = 1 << size_l2
            sx = self.flash.read(size, 256)
            self.logger.info("At %#010x: %s", size, sx.hex())
            if sx == s0:
                smallest = size
        size = smallest
        self.logger.info("Flash size %d MB", size >> 20)
        self.flash.size = size
        self.detach()
        
    def detach(self):
        super().detach()
        self.interface.enter_cmd_xip()
        self.interface.exclusive_access(1)

    def attach(self):
        super().attach()
        self.interface.exclusive_access(0)
        self.interface.exit_xip()

    def reset(self):
        self.interface.reboot(0, 0, 100)
