from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(0x010220, 0x010219, 0x012018)
class S25FL(SfdpFlash):
    max_freq = 106e6
    CMD_READ_OTP = b"\x4b"
    write_buffer_size = 256

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "S25FL")
        self.uid = self.command(self.CMD_READ_OTP + b"\x00\x00\x00\x00", 16)
        self.logger.info("Device UID: %s", binascii.b2a_hex(self.uid))
