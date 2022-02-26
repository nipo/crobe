from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(0x9d4014, 0x9d4015, 0x9d4016)
class Is25Lq(SfdpFlash):
    max_freq = 106e6
    CMD_READ_UID = b"\x4b"
    write_buffer_size = 256

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "IS25LQ")
        self.uid = self.command(self.CMD_READ_UID, arg = b"\x00\x00\x00\x00", rsize = 16)
        self.logger.note("Device UID: %s", binascii.b2a_hex(self.uid))
