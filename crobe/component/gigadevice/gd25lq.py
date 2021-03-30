from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(0xc86018)
class Gd25lq(SfdpFlash):
    CMD_READ_UID = b"\x4b"
    write_buffer_size = 256

    def start(self):
        super().start()
        print("Status: %02x %02x" % (self.status, self.command(b'\x35', rsize = 1)[0]))
        self.uid = self.command(self.CMD_READ_UID, rsize = 8, dummy_words = 4)
        self.logger.info("Device UID: %s", self.uid.hex())
