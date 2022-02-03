from ..spi_flash import SpiPSRam
from ...db import NoMatch

class APSxx04(SpiPSRam):
    PARTS = {
        0: dict(page_size = 512, fmax = 133),
        2: dict(page_size = 1024, fmax = 84),
    }
    def __init__(self, port, mideid):
        density_code = mideid[2] >> 5
        mbits = 16 << ((density_code) & 0x7)

        self.mid = mideid[:2]
        self.eid = mideid[2:]
        info = self.PARTS.get(density_code, self.PARTS[0])
        self.write_buffer_size = info["page_size"]
        self.total_size = mbits << (20 - 3)
        self.max_freq = info["fmax"] * 1e6

        SpiPSRam.__init__(self, port, int.from_bytes(mideid[:3], "big") & 0xffffe0, "APS%02d04" % mbits)
        self.logger.info("EID: %s", self.eid.hex())
        

@SpiPSRam.db.register(0xfffffe)
def ap_psram_discover(port, idr):

    idr = port.cmd_shift(8)
    port.execute([port.cmd_cs(True),
            port.cmd_shift(b"\x9f\x00\x00\x00", read_miso = False),
            idr,
            port.cmd_cs(False),
    ])
    mideid = idr.miso[:2]
    if mideid == b"\x0d\x5d":
        return APSxx04(port, idr.miso)
    return db.NoMatch(mideid)
