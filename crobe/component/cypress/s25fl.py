from ..spi_flash import SfdpFlash, SpiFlash
import binascii

@SfdpFlash.db.register(0x010220, 0x010219, 0x012018)
class S25FL(SfdpFlash):
    max_freq = 106e6
    CMD_READ_OTP = b"\x4b"
    write_buffer_size = 512
    CMD_WRITE_STATUS = b'\x01'

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "S25FL")
        self.uid = self.command(self.CMD_READ_OTP + b"\x00\x00\x00\x00", 16)
        self.logger.info("Device UID: %s", binascii.b2a_hex(self.uid))

@SfdpFlash.db.register(0x014013)
class S25FL204(SpiFlash):
    max_freq = 44e6

    CMD_WRITE_STATUS = b'\x01'
    CMD_RESET_ENABLE = None
    CMD_RESET = None
    CMD_4KB_ERASE = b'\x20'
    SECTOR_INFO = [
        {"type": 1, "size": 4 * 1024, "erase_cmd": b'\x20'},
        {"type": 2, "size": 64 * 1024, "erase_cmd": b'\xd8'},
        ]
    write_buffer_size = 512
    total_size = 4 * 1024 * 1024 / 8

    def __init__(self, port, idr):
        SpiFlash.__init__(self, port, idr, "S25FL204")
