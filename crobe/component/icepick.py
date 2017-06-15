from ..part_id import PartId
from ..adapter import jtag

@jtag.Tap.db.register(PartId(0, 0x17, 0x1ce))
class IcePick(jtag.Tap):
    irlen = 6

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "Ti ICE-Pick"

    def start(self):
        self.idcode = PartId.from_idcode(self.dr_shift(0x4, 0, 32))
        self.icepick_id = self.dr_shift(0x5, 0, 32)
        self.user_code = self.dr_shift(0x8, 0, 32)

        self.logger.info("IDCode: %s", self.idcode)
        self.logger.info("User Code: 0x%08x", self.user_code)
        self.logger.info("ICEPick-ID: 0x%08x", self.icepick_id)

        self.dr_shift(7, 0x89, 8, read_tdo = False)
        self.dr_shift(2, 0xa0120008, 32, read_tdo = False)
        self.dr_shift(2, 0xa0122108, 32, read_tdo = False)
        self.run(50)

        self.insert_before(PartId(4, 0x3b, 0xba00))
        self.logger.info("Insert done")

        jtag.Tap.start(self)

