from .model import Bus
from ..protocol import i2c
import binascii
import time

__all__ = ["I2cMem"]

class I2cMem(i2c.Slave, Bus):
    def __init__(self, bus, saddr, addr_bytes = 2, size = None, page_size = None, saddr_bits = 0):
        i2c.Slave.__init__(self, bus, "I2cMem", saddr)
        Bus.__init__(self, self.name)
        self.addr_bytes = addr_bytes
        self.saddr_bits = saddr_bits
        self.size = size
        self.page_size = page_size

    def start(self):
        super().start()
        max_size = 1 << (self.addr_bytes * 8 + self.saddr_bits)
        if self.size is None:
            self.size = max_size
        if self.page_size is None:
            self.page_size = 16

        if self.size > max_size:
            raise ValueError("Memory size is more than accessible addresses")
        
    def _addr(self, addr):
        baddr = (addr & ((1 << (self.addr_bytes * 8)) - 1)).to_bytes(self.addr_bytes, 'big')
        saddr = (self.saddr & ~((1 << self.saddr_bits) - 1)) + (addr >> (self.addr_bytes * 8))
        print(addr, baddr, saddr)
        return saddr, baddr

    def read(self, addr, size):
        read_by = min(self.page_size, size, 32)
        assert addr + size <= self.size, (addr, size, self.size)

        r = b''
        for off in range(addr, addr + size, read_by):
            chunk = self._read(off, read_by)
            r += chunk
        return r[:size]

    def write(self, addr, data):
        assert addr + len(data) <= self.size

        if addr % self.page_size:
            size = -addr % self.page_size
            self._write(addr, data[:size])
            data = data[size:]
            addr += size

        for off in range(0, len(data), self.page_size):
            chunk = data[off : off + self.page_size]
            self._write(addr + off, chunk)

    def mem_read(self, address, size):
        return self.read(address, size)

    def mem_write(self, address, data):
        return self.write(address, data)

    def _read(self, addr, size):
        saddr, baddr = self._addr(addr)
        wa = self.port.cmd_write(saddr, baddr)
        ro = self.port.cmd_read(saddr, size)
        self.port.execute([wa, ro])
        return ro.data
    
    def _write(self, addr, data):
        assert 0 < len(data) <= self.page_size
        assert addr // self.page_size == (addr + len(data) - 1) // self.page_size

        saddr, baddr = self._addr(addr)
        self.port.execute([self.port.cmd_write(saddr, baddr + data)])

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr_bits':
            self.saddr_bits = int(v, 16)
        elif k == 'addr_bytes':
            self.addr_bytes = int(v)
        elif k == 'size':
            self.size = int(v, 0)
        elif k == 'page_size':
            self.page_size = int(v)
        else:
            return i2c.Slave.option_set(self, opt)

class I2cEeprom(I2cMem):
    def _write(self, addr, data):
        assert 0 < len(data) <= self.page_size
        assert addr // self.page_size == (addr + len(data) - 1) // self.page_size

        deadline = time.time() + .1
        while True:
            try:
                return I2cMem._write(self, addr, data)
            except i2c.AddressNack:
                if time.time() < deadline:
                    time.sleep(.001)
                    continue
                raise

    def _read(self, addr, size):
        assert 0 < size <= self.page_size
        assert addr // self.page_size == (addr + size - 1) // self.page_size

        deadline = time.time() + .1
        while True:
            try:
                return I2cMem._read(self, addr, size)
            except i2c.AddressNack:
                if time.time() < deadline:
                    time.sleep(.001)
                    continue
                raise

@i2c.Interface.db.register("m24m02")
def m24m02(bus):
    return I2cEeprom(bus, None,
                     addr_bytes = 2,
                     saddr_bits = 2,
                     page_size = 256)

@i2c.Interface.db.register("24lc128")
def _24lc128(bus):
    return I2cEeprom(bus, None,
                     addr_bytes = 2,
                     page_size = 64)

@i2c.Interface.db.register("24lc08")
def _24lc08(bus):
    return I2cEeprom(bus, 0x50,
                     addr_bytes = 1,
                     saddr_bits = 2,
                     page_size = 16)

@i2c.Interface.db.register("pca24s08")
def _pca24s08(bus):
    return I2cEeprom(bus, 0x54,
                     addr_bytes = 1,
                     saddr_bits = 2,
                     page_size = 16)

@i2c.Interface.db.register("pca24s08_prot")
def _pca24s08_prot(bus):
    return I2cEeprom(bus, 0x5c,
                     addr_bytes = 1,
                     page_size = 1,
                     size = 32)

@i2c.Interface.db.register("eeprom")
def i2c_eeprom_gen(bus):
    return I2cEeprom(bus, None)

@i2c.Interface.db.register("memory")
def i2c_mem_gen(bus):
    return I2cMem(bus, None)
