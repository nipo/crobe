from ..model import PortComponent
from ..adapter.protocol import i2c
import binascii

__all__ = ["I2cEeprom"]

class I2cEeprom(PortComponent):
    def __init__(self, bus, saddr, addr_bytes = 2, size = None, page_size = None):
        PortComponent.__init__(self, bus, "I2cEeprom")
        self.saddr = saddr
        self.addr_bytes = addr_bytes
        self.size = 1 << (addr_bytes * 8) if size is None else size
        self.page_size = self.size if page_size is None else page_size

    def read(self, addr, size):
        assert addr + size <= self.size

        baddr = addr.to_bytes(self.addr_bytes, 'big')

        return self.port.write_read(self.saddr, baddr, size)

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

    def _write(self, addr, data):
        assert 0 < len(data) <= self.page_size

        addr = addr.to_bytes(self.addr_bytes, 'big')
        return self.port.write(self.saddr, addr + data)

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
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
