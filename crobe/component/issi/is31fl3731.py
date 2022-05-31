from ...model import PortComponent
from ...protocol import i2c

@i2c.Interface.db.register("is31fl3731")
class Is31fl3731(i2c.Slave):
    INDEX = {}

    for cathode in range(1, 10):
        for channel in ["A", "B"]:
            for anode in range(1, 10):
                if anode == cathode:
                    continue
                INDEX[(channel, anode, cathode)] = len(INDEX)
    
    def __init__(self, bus, saddr = None):
        self.__page = None
        i2c.Slave.__init__(self, bus, "IS31FL3731", saddr)

    def page_select(self, page):
        if self.__page == page:
            return
        self.__page = page
        self.write(bytes([0xfd, page]))

    def paged_write(self, page, addr, data):
        self.page_select(page)
        self.write(bytes([addr]) + data)

    def paged_read(self, page, addr, size):
        self.page_select(page)
        return self.write_read(bytes([addr]), size)

    def chip_enable(self, enable):
        self.paged_write(0xb, 0xa, bytes([int(enable)]))

    def led_enable_set(self, no, enable):
        en = self.paged_read(0x0, no // 8, 1)[0]
        if enable:
            en |= 1 << (no & 7)
        else:
            en &= ~(1 << (no & 7))
        self.paged_write(0x0, no // 8, bytes([en]))

    def led_brightness_set(self, no, bright):
        self.paged_write(0x0, 0x24 + no, bytes([bright]))

    def init(self):
        self.paged_write(0xb, 0x0, b"\x00" * 13)
        self.paged_write(0x0, 0x0, b"\x00" * 0xb4)
        self.chip_enable(True)
        
    def led_set(self, channel, anode, cathode, value):
        index = self.INDEX[(channel, anode, cathode)]
        self.led_brightness_set(index, value)

    def led_enable(self, channel, anode, cathode, on = True):
        index = self.INDEX[(channel, anode, cathode)]
        self.led_enable_set(index, on)
