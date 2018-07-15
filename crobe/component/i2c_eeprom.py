from ..model import PortComponent
from .model import Bus
from ..protocol import i2c
import binascii
import time

__all__ = ["I2cEeprom"]

class I2cEeprom(PortComponent, Bus):
    def __init__(self, bus, saddr, addr_bytes = 2, size = None, page_size = None, saddr_bits = 0):
        PortComponent.__init__(self, bus, "I2cEeprom")
        Bus.__init__(self, self.name)
        self.saddr = saddr
        self.addr_bytes = addr_bytes
        self.saddr_bits = saddr_bits

        max_size = 1 << (addr_bytes * 8 + saddr_bits)
        self.size = size or max_size
        self.page_size = page_size or self.size

        if self.size > max_size:
            raise ValueError("EEPROM size is more than accessible addresses")

    def _addr(self, addr):
        baddr = (addr & ((1 << (self.addr_bytes * 8)) - 1)).to_bytes(self.addr_bytes, 'big')
        saddr = self.saddr + (addr >> (self.addr_bytes * 8))
        return saddr, baddr

    def read(self, addr, size):
        assert addr + size <= self.size, (addr, size, self.size)

        saddr, baddr = self._addr(addr)

        return self.port.write_read(saddr, baddr, size)

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

    def _write(self, addr, data):
        assert 0 < len(data) <= self.page_size

        saddr, baddr = self._addr(addr)

        deadline = time.time() + .1
        while time.time() < deadline:
            try:
                return self.port.write(saddr, addr + data)
            except i2c.AddressNack:
                continue

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
        elif k == 'saddr_bits':
            self.saddr_bits = int(v, 16)
        elif k == 'addr_bytes':
            self.addr_bytes = int(v)
        elif k == 'size':
            self.size = int(v)
        elif k == 'page_size':
            self.page_size = int(v)
        else:
            return PortComponent.option_set(opt)

@i2c.Interface.db.register("eeprom")
def i2c_eeprom_gen(bus):
    return I2cEeprom(bus, 0)
