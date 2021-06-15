from ..spi_flash import SpiFlash, SfdpFlash
import binascii
import time

@SpiFlash.db.register(0xef3013)
class W25x(SpiFlash):
    max_freq = 80e6
    
    CMD_STATUS_WRITE_ENABLE = b'\x50'
    CMD_WRITE_STATUS = b'\x01'
    CMD_RESET_ENABLE = None
    CMD_RESET = None
    CMD_4KB_ERASE = b'\x20'
    SECTOR_INFO = [
        {"type": 1, "size": 4 * 1024, "erase_cmd": b'\x20', "time": 0.3},
        {"type": 2, "size": 32 * 1024, "erase_cmd": b'\x52', "time": 0.8},
        {"type": 3, "size": 64 * 1024, "erase_cmd": b'\xd8', "time": 1.},
        ]
    page_size = 256
    write_buffer_size = 256
    total_size = 4 * 1024 * 1024 / 8

    def __init__(self, port, idr):
        SpiFlash.__init__(self, port, idr, "W25Xxx")
#        self.command(b'\xab', dummy_words = 6)

    def erase_sector(self, addr, si):
        self.unprotect()
        self.write_enable(True)
        self.logger.info("Erasing %d bytes at %08x (%02x)", si["size"], addr, si["erase_cmd"][0])
        self.command(si["erase_cmd"], arg = self.addr(addr))
        time.sleep(si["time"])
        while self.status & self.STATUS_WIP:
            pass

    def page_program(self, addr, data):
        self.write_enable(True)
        self.command(self.CMD_PAGE_PROGRAM, arg = self.addr(addr), wdata = data)
        time.sleep(.001)
        while self.status & self.STATUS_WIP:
            time.sleep(.01)

    def unprotect(self):
        self.command(self.CMD_STATUS_WRITE_ENABLE)
        SpiFlash.unprotect(self)
        time.sleep(.02)


@SpiFlash.db.register(0xef7018)
class W25Q(SfdpFlash):
    page_size = 256
    write_buffer_size = 256
