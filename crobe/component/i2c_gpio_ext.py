from .model import Bus
from ..protocol import i2c, bitbang

__all__ = ["Pcal6524"]

class IoInfo(bitbang.IoInfo):
    def __init__(self, name, no):
        self.name = name
        self.no = no
        self.mode = bitbang.Mode.Input
        self.value = False

class Pcal6524(i2c.Slave, bitbang.Interface):
    INPUT = 0x00
    OUTPUT = 0x04
    POLARITY = 0x08
    CONFIG = 0x0c
    DRIVE_STRENGTH = 0x40
    INPUT_LATCH = 0x48
    PULL_EN = 0x4c
    PULL_SEL = 0x50
    IRQ_MASK = 0x54
    IRQ_STATUS = 0x58
    OUTPUT_PORT = 0x5c
    IRQ_EDGE = 0x60
    IRQ_CLEAR = 0x68
    INPUT_STATUS = 0x5c
    PIN_OUT_CONFIG = 0x70
    DEBOUNCE = 0x74
    # Can be or-ed with others, increment beyond 2 lsb
    AUTOINC = 0x80

    def __init__(self, bus, saddr = None):
        i2c.Slave.__init__(self, bus, "PCAL6524", saddr)
        bitbang.Interface.__init__(self, bus, self.name)
        self.reg_cache = {}

    def start(self):
        i2c.Slave.start(self)
        bitbang.Interface.start(self)
        self._cache_refresh()

    def _cache_refresh(self):
        regs = [self.INPUT, self.OUTPUT, self.CONFIG, self.PULL_EN, self.PULL_SEL]
        cmds = [self.cmd_reg24_read(r) for r in regs]
        self.execute(cmds)
        for r, c in zip(regs, cmds):
            self.reg_cache[r] = int.from_bytes(c.data, "little")

    def _io_info_from_cache(self, no):
        mask = 1 << no
        is_in = bool(self.reg_cache[self.CONFIG] & mask)
        out_val = bool(self.reg_cache[self.OUTPUT] & mask)
        in_val = bool(self.reg_cache[self.INPUT] & mask)
        pull_en = bool(self.reg_cache[self.PULL_EN] & mask)
        pull_val = bool(self.reg_cache[self.PULL_SEL] & mask)

        return IoInfo(f"io{no}", no,
                      mode = bitbang.Mode.Input if is_in else bitbang.Mode.D0D1,
                      value = in_val if is_in else out_val)
            
    def io_info(self):
        ret = {}
        for i in range(24):
            io = self._io_info_from_cache(io)
            ret[io.name] = io
        return ret

    def cmd_reg24_write(self, base, data):
        return self.cmd_write(bytes([base]) + data)

    def cmd_reg24_read(self, base):
        return self.cmd_write_read(bytes([base]), 3)

    def cmd_reg48_write(self, base, data):
        return self.cmd_write(bytes([self.AUTOINC | base]) + data)

    def cmd_reg48_read(self, base):
        return self.cmd_write_read(bytes([self.AUTOINC | base]), 6)

class Pcal6408a(i2c.Slave):
    INPUT = 0x00
    OUTPUT = 0x01
    POLARITY = 0x02
    CONFIG = 0x03

    def __init__(self, bus, saddr = None):
        i2c.Slave.__init__(self, bus, "PCAL6408A", saddr)
        self.reg_cache = {}
        
    def start(self):
        i2c.Slave.start(self)
        self._cache_refresh()

    def _cache_refresh(self):
        regs = [self.INPUT, self.OUTPUT, self.CONFIG]
        for r in regs:
            c = self.reg_read(r)
            self.reg_cache[r] = c

    def reg_write(self, reg, val):
        if reg in self.reg_cache:
            self.reg_cache[reg] = val
        return self.write(bytes([reg, val]))

    def reg_read(self, base):
        return self.write_read(bytes([base]), 1)[0]

    def out_set(self, data, mask = 0xff):
        val = (data & mask) | (self.reg_cache[self.OUTPUT] & ~mask)
        self.reg_write(self.OUTPUT, val)

    def oen_set(self, data, mask = 0xff):
        val = (data & mask) | (self.reg_cache[self.CONFIG] & ~mask)
        self.reg_write(self.CONFIG, val)

    def in_get(self):
        return self.reg_read(self.INPUT)
