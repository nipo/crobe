from ..spi_flash import SfdpFlash
import binascii

@SfdpFlash.db.register(*[0xc22800 | x for x in range(0x10, 0x18)])
class Is25Lq(SfdpFlash):
    max_freq = 106e6

    def __init__(self, port, idr):
        SfdpFlash.__init__(self, port, idr, "M25Rxxx")
