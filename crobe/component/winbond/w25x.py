from ..spi_flash import SpiFlash, SfdpFlash
import binascii

@SpiFlash.db.register(0xef3013)
class W25x(SpiFlash):
    max_freq = 80e6
    
    CMD_STATUS_WRITE_ENABLE = b'\x50'
    CMD_WRITE_STATUS = b'\x01'
    CMD_RESET_ENABLE = None
    CMD_RESET = None
    CMD_4KB_ERASE = b'\x20'
    SECTOR_INFO = [
        {"type": 1, "size": 4 * 1024, "erase_cmd": b'\x20'},
        {"type": 2, "size": 32 * 1024, "erase_cmd": b'\x52'},
        {"type": 3, "size": 64 * 1024, "erase_cmd": b'\xd8'},
        ]
    page_size = 256
    write_buffer_size = 256
    total_size = 4 * 1024 * 1024 / 8

    def __init__(self, port, idr):
        SpiFlash.__init__(self, port, idr, "W25Xxx")

    def unprotect(self):
        self.command(self.CMD_STATUS_WRITE_ENABLE)
        SpiFlash.unprotect(self)

@SpiFlash.db.register(0xef7018)
class W25Q(SfdpFlash):
    page_size = 256
    write_buffer_size = 256
