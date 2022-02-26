from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(0x1f4218)
class At25sl(SfdpFlash):
    CMD_READ_UID = b"\x4b"

    def start(self):
        super().start()
        self.logger.debug("Status: %02x %02x" % (self.status, self.command(b'\x35', rsize = 1)[0]))
        self.uid = self.command(self.CMD_READ_UID, rsize = 8, dummy_words = 4)
        self.logger.note("Device UID: %s", self.uid.hex())
