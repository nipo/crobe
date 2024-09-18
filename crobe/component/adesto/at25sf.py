from ..spi_flash import SpiFlash, SfdpFlash
import binascii

@SpiFlash.db.register(0x1f8401)
class At25sf(SpiFlash):
    max_freq = 85e6

    CMD_CHIP_ERASE = b'\x60'
    CMD_WRITE_STATUS = b'\x01'
    CMD_WRITE_VOLATILE_STATUS = b'\x50'
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

    def start(self):
        SpiFlash.start(self)
        print("Status: %02x %02x" % (self.status, self.command(b'\x35', rsize = 1)[0]))

@SpiFlash.db.register(0x1f8901)
class At25sf(SfdpFlash):
    page_size = 256
    write_buffer_size = 256
