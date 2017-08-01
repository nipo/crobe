from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(0x9d4014, 0x9d4015, 0x9d4016)
class Is25Lq(SfdpFlash):
    CMD_READ_UID = b"\x4b"

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "IS25LQ")
        self.uid = self.command(self.CMD_READ_UID + b"\x00\x00\x00\x00", 16)
        self.logger.info("Device UID: %s", binascii.b2a_hex(self.uid))
