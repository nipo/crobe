from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(*[0xc22800 | x for x in range(0x10, 0x18)])
@SfdpFlash.db.register(0xc22539)
class M25Rxxx(SfdpFlash):

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "M25Rxxx")
