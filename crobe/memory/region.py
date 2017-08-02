from .. import model
from enum import Enum

class Flag(Enum):
    WRITABLE      = 1
    MM_READ       = 2
    MM_WRITE      = 3
    PARTIAL_READ  = 4
    PARTIAL_WRITE = 5
    VOLATILE      = 6
    ERASE_ONE     = 7
    ERASE_ZERO    = 8

class Type(Enum):
    RAM = 0
    FLASH = 1
    REGS = 2

class Region(model.BusComponent):
    flags = set()
    type = None # Should be a Type

    def __init__(self, bus, name, address, size):
        model.BusComponent.__init__(self, bus, name)
        self.address = address
        self.size = size

    def __lt__(self, other):
        return self.address < other.address

    def __lte__(self, other):
        return self.address <= other.address

    def __str__(self):
        return "Memory %s '%s' from 0x%08x to 0x%08x (%.0f KiB)" % (
            self.type.name, self.name,
            self.address, self.address + self.size, self.size / 1024)
    
class Flash(Region):
    type = Type.FLASH
    flags = set([Flag.MM_READ,
                 Flag.PARTIAL_READ,
                 Flag.WRITABLE])

    def __init__(self, bus, name, address, size, page_size):
        Region.__init__(self, bus, name, address, size)
        self.page_size = page_size

    def erase(self, addr, size):
        raise NotImplementedError()

    def flash(self, program):
        raise NotImplementedError()

    def verify(self, program):
        for s in program.paged(self.page_size):
            self.logger.info("Checking range 0x%08x-0x%08x", s.address, s.address + len(s))
            flash_data = self.bus.mem_read(s.address, len(s))
            diffs = 0
            for orig, found in zip(s.data, flash_data):
                diffs += int(orig != found)

            if diffs:
                self.logger.error("Comparison for %s failed: %d/%d bytes differ", s, diffs, len(s))
                return False
        return True
    
    def __str__(self):
        return Region.__str__(self) + ", %dB pages" % self.page_size

class NandFlash(Flash):
    flags = Flash.flags | set([Flag.ERASE_ONE])

class NorFlash(Region):
    flags = Flash.flags | set([Flag.ERASE_ZERO])

class Ram(Region):
    flags = set([Flag.MM_WRITE,
                 Flag.MM_READ,
                 Flag.PARTIAL_WRITE,
                 Flag.PARTIAL_READ,
                 Flag.VOLATILE,
                 Flag.WRITABLE])
    type = Type.RAM

class Peripheral(Region):
    flags = set([Flag.MM_WRITE,
                 Flag.MM_READ,
                 Flag.PARTIAL_WRITE,
                 Flag.PARTIAL_READ,
                 Flag.VOLATILE,
                 Flag.WRITABLE])
    type = Type.REGS
