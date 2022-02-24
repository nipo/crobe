from ..loadable.object import Program, Segment
from .. import model
from enum import Enum
from ..util.pretty import base2
import binascii
import time

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

    def contains(self, addr):
        return self.address <= addr < self.address + self.size
    
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
        with self.logger.progress("Checking", len(pages)) as progress:
            for s in progress.iterate(pages):
                flash_data = self.read(s.address - self.address, len(s))
                diffs = 0
                for orig, found in zip(s.data, flash_data):
                    diffs += int(orig != found)

                if diffs:
                    self.logger.error("Comparison for %s failed: %d/%d bytes differ", s, diffs, len(s))
                    dumped = 0
                    for off in range(0, len(s.data), 16):
                        a = s.data[off:off+16]
                        b = flash_data[off:off+16]
                        if a == b:
                            continue
                        self.logger.error("Expect 0x%08x %s", s.address + off, binascii.b2a_hex(a))
                        self.logger.error("Memory 0x%08x %s", s.address + off, binascii.b2a_hex(b))

                        dumped += 1
                        if dumped >= 10:
                            break
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
            self.logger.trace("Checking range 0x%08x-0x%08x", s.address, s.address + len(s))
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

    def read(self, begin = 0, end = None):
        total_size = 0
        to_read = []
        if end is None:
            end = 0
            for region in self.children_of_class(Region):
                end = max(end, region.address + region.size)

        for region in self.children_of_class(Region):
            #if region.type not in [Type.FLASH, Type.EEPROM]:
            #    continue
            if not (region.flags & set([Flag.PARTIAL_READ, Flag.MM_READ])):
                continue
            roff = max(0, begin - region.address)
            rend = min((region.address + region.size, end))
            rsize = max(0, rend - region.address)
            if not rsize:
                continue
            total_size += rsize
            to_read.append((region, roff, rsize))

        with self.logger.progress("Reading", total_size) as progress:
            p = Program()
            for region, off, s in to_read:
                try:
                    cs = region.page_size
                except AttributeError:
                    cs = 1024

                blob = bytearray()
                for offset in range(0, s, cs):
                    chunk = region.read(off + offset, min(cs, s - offset))
                    blob += chunk

                    progress.step(len(chunk))

                p.append(Segment(region.address + off, blob))
        return p

    def attach(self):
        pass

    def detach(self):
        pass

    def erase_all(self):
        flashes = self.children_of_class(Flash)
        for f in flashes:
            f.erase(0, f.size)
        self.force_blank()

    def program_begin(self, do_erase, assume_clean):
        if do_erase:
            self.erase_all()
        if assume_clean:
            self.force_blank()

    def program_end(self, success, do_start):
        if do_start:
            if not success:
                return
            try:
                self.reset()
            except AttributeError:
                print("WARNING: Target does not handle reset")

    def write(self, program,
              do_erase = False,
              do_verify = False,
              do_start = False,
              assume_clean = False):
        self.program_begin(do_erase, assume_clean)

        to_erase = []
        to_flash = []

        for r in self.children_of_class(Region):
            region_program = program.within(r.address, r.address + r.size)

            if not region_program:
                continue

            if not r.is_blank and region_program:
                r0 = []
                for p in region_program:
                    r0.append((p.address - r.address, len(p)))
                r0.sort()
                r1 = [r0.pop(0)]
                for r2 in r0:
                    if r1[-1][0] + r1[-1][1] >= r2[0]:
                        r1[-1] = r1[-1][0], r2[0] + r2[1]
                    else:
                        r1.append(r2)
                for r2 in r1:
                    to_erase.append((r, r2[0], r2[1]))

            if hasattr(r, "page_size"):
                region_program = region_program.paged(r.page_size)
            for p in region_program:
                to_flash.append((r, p.address - r.address, p.data))

        with self.logger.progress("Erasing", len(to_erase)) as progress:
            for r, addr, size in progress.iterate(to_erase):
                r.erase(addr, size)

        with self.logger.progress("Writing", len(to_flash)) as progress:
            for r, offset, data in progress.iterate(to_flash):
                r.write(offset, data)

        success = True
        if do_verify:
            success = self.verify(program)

        self.program_end(success, do_start)

    def verify(self, program):
        regions = self.children_of_class(Region)
        to_check = []

        for region in regions:
            programmed = program.within(region.address, region.address + region.size)
            to_check.append((region, programmed))

        total_size = sum(sum(len(s) for s in p) for (r, p) in to_check)

        count = 0

        with self.logger.progress("Checking", len(to_check)) as progress:
            for region, programmed in progress.iterate(to_check):
                with self.logger.progress(region.name, programmed.size) as rprogress:
                    for segment in programmed:
                        for off in range(0, len(segment), 4096):
                            ssize = min(len(segment) - off, 4096)

                            self.logger.trace("Reading 0x%x +0x%x", segment.address + off, ssize)
                            actual = region.read(segment.address - region.address + off, ssize)
                            rprogress.step(ssize)
                            if actual != segment.data[off : off + ssize]:
                                self.logger.error("Mismatch in %s", segment)
                                for off2 in range(0, ssize, 16):
                                    orig = segment.data[off + off2 : off + off2 + 16]
                                    rb = actual[off2 : off2 + 16]
                                    if orig == rb:
                                        continue
                                    self.logger.error("Expected %08x: %s",
                                                      segment.address + off + off2,
                                                      str(binascii.b2a_hex(orig), "ascii"))
                                    self.logger.error("Readback         : %s",
                                                      str(binascii.b2a_hex(rb), "ascii"))
                                    count += 1
                                    if count > 3:
                                        return False
        return True
