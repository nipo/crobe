from ..spi_flash import SpiFlash
import binascii

@SpiFlash.db.register(0x1f8401)
class At25sf(SpiFlash):
    max_freq = 50e6
    
    CMD_WRITE_STATUS = b'\x50'
    CMD_RESET_ENABLE = None
    CMD_RESET = None
    CMD_4KB_ERASE = b'\x20'
    SECTOR_INFO = [
        {"type": 1, "size": 4 * 1024, "erase_cmd": b'\x20'},
        {"type": 2, "size": 32 * 1024, "erase_cmd": b'\x52'},
        {"type": 3, "size": 64 * 1024, "erase_cmd": b'\xd8'},
        ]
    page_size = 256
    total_size = 4 * 1024 * 1024 / 8
    write_buffer_size = 256

    def __init__(self, port, idr):
        SpiFlash.__init__(self, port, idr, "AT25SFxx")
