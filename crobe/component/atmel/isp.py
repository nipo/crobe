from ...adapter.protocol import spi
import struct
import time

class Isp(spi.Target):
    def __init__(self, port, name = None):
        spi.Target.__init__(self, name or "ISP", port)

    def command(self, *data):
        assert len(data) <= 4
        b = bytes(list(data) + ([0] * (4 - len(data))))
        return self.port.shift(b)

    def enable(self):
        self.port.reset = False
        time.sleep(.1)
        self.port.reset = True
        ret = self.command(0xac, 0x53)
        assert ret[2] == 0x53

    def device_signature_read(self):
        cmds = []
        for i in range(3):
            cmds.append(self.port.cmd_shift(bytes([0x30, 0, i, 0])))
        self.port.execute(cmds)
        return int.from_bytes(bytes([c.miso[-1] for c in cmds]), byteorder = "big")

    def chip_erase(self):
        return self.command(0xac, 0x80)

    def program_read_word(self, addr):
        h = addr & 1
        a = (addr >> 9) & 0xff
        b = (addr >> 1) & 0xff

        return self.command(0x20 | (h << 3), a, b)[-1]

    def program_mem_read(self, base, size):
        cmds = []
        for addr in range(base, base + size):
            h = addr & 1
            a = (addr >> 9) & 0xff
            b = (addr >> 1) & 0xff

            cmds.append(self.port.cmd_shift(bytes([0x20 | (h << 3), a, b, 0])))
        self.port.execute(cmds)

        return bytes([c.miso[-1] for c in cmds])

    def program_page_data_load(self, data):
        assert len(data) <= 256
        cmds = []
        for addr, b in enumerate(data):
            h = addr & 1
            a = (addr >> 9) & 0xff

            cmds.append(self.port.cmd_shift(bytes([0x40 | (h << 3), 0, a, b])))
        self.port.execute(cmds)

    def program_page_data_save(self, address):
        self.command(0x43, (address >> 9) & 0xff, (address >> 1) & 0x80, 0)

    def program_mem_write(self, base, data):
        assert not (base & 0xff)

        for addr in range(0, base, 256):
            self.program_page_data_load(data[addr : addr + 256])
            self.program_page_data_save(addr)
