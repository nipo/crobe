from ..loadable.object import Program, Segment
from .. import model
from enum import Enum
from ..util.pretty import base2
import click

__all__ = ["Region", "Flash", "NandFlash", "NorFlash", "Eeprom", "Ram", "Peripheral", "Loadable", "Flag", "Type"]

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
    EEPROM = 2
    REGS = 3

class Region(model.Component):
    flags = set()
    type = None # Should be a Type
    is_blank = False

    def __init__(self, name, address, size):
        model.Component.__init__(self, name)
        self.address = address
        self.size = int(size)

    def __lt__(self, other):
        return self.address < other.address

    def __lte__(self, other):
        return self.address <= other.address

    def __str__(self):
        return "Memory %s '%s' from 0x%08x to 0x%08x (%s)" % (
            self.type.name, self.name,
            self.address, self.address + self.size, base2(self.size, "B"))
    
class Flash(Region):
    type = Type.FLASH
    flags = set([Flag.MM_READ,
                 Flag.PARTIAL_READ,
                 Flag.WRITABLE])

    def __init__(self, name, address, size, page_size):
        Region.__init__(self, name, address, size)
        self.page_size = page_size
        self.__blank = False

    @property
    def is_blank(self):
        return self.__blank

    @is_blank.setter
    def is_blank(self, blank = True):
        self.__blank = blank

    def erase(self, offset, size):
        raise NotImplementedError()

    def write(self, offset, data):
        raise NotImplementedError()

    def read(self, offset, size):
        raise NotImplementedError()

    def verify(self, program):
        pages = program.paged(self.page_size)
        with click.progressbar(pages, label = "Checking") as bar:
            for s in bar:
                flash_data = self.read(s.address - self.address, len(s))
                diffs = 0
                for orig, found in zip(s.data, flash_data):
                    diffs += int(orig != found)

                if diffs:
                    self.logger.error("Comparison for %s failed: %d/%d bytes differ", s, diffs, len(s))
                    return False
        return True
    
    def __str__(self):
        return "%s, %s pages" % (Region.__str__(self), base2(self.page_size, "B"))

class Eeprom(Region):
    type = Type.EEPROM
    flags = set([Flag.PARTIAL_READ,
                 Flag.PARTIAL_WRITE,
                 Flag.WRITABLE])

    def __init__(self, name, address, size):
        Region.__init__(self, name, address, size)

    @property
    def is_blank(self):
        return False

    @is_blank.setter
    def is_blank(self, blank = True):
        pass

    def erase(self, offset, size):
        pass

    def write(self, offset, data):
        raise NotImplementedError()

    def read(self, offset, size):
        raise NotImplementedError()

    def verify(self, program):
        for s in program:
            self.logger.debug("Checking range 0x%08x-0x%08x", s.address, s.address + len(s))
            flash_data = self.read(s.address - self.address, len(s))
            diffs = 0
            for orig, found in zip(s.data, flash_data):
                diffs += int(orig != found)

            if diffs:
                self.logger.error("Comparison for %s failed: %d/%d bytes differ", s, diffs, len(s))
                return False
        return True

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

    def erase(self, offset, size):
        pass

class Peripheral(Region):
    flags = set([Flag.MM_WRITE,
                 Flag.MM_READ,
                 Flag.PARTIAL_WRITE,
                 Flag.PARTIAL_READ,
                 Flag.VOLATILE,
                 Flag.WRITABLE])
    type = Type.REGS

    def erase(self, offset, size):
        pass

class Loadable:
    def __init__(self):
        pass

    def force_blank(self):
        for region in self.children_of_class(Region):
            region.is_blank = True

    def read(self, address, size):
        regions = self.children_of_class(Region)
        p = Program()
        for r in regions:
            if not isinstance(r, Flash):
                continue

            p.append(Segment(r.address, ))

    def erase_all(self):
        flashes = self.children_of_class(Flash)
        for f in flashes:
            f.erase(0, f.size)
        self.force_blank()

    def write(self, program):
        regions = self.children_of_class(Region)
        for r in regions:
            blank = r.is_blank

            pages = program.within(r.address, r.address + r.size)
            if not blank:
                r.erase(pages.address - r.address, pages.end - pages.address)

            with click.progressbar(pages, label = "Writing %-8s" % r.name) as bar:
                for p in bar:
                    r.write(p.address - r.address, p.data)

    def verify(self, program):
        regions = self.children_of_class(Region)
        for r in regions:
            if not isinstance(r, Flash):
                continue

            pages = program.within(r.address, r.address + r.size)
            if not r.verify(pages):
                return False
        return True
