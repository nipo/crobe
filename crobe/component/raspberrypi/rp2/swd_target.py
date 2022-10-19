from ....part_id import PartId
from ....protocol import swd
from ...arm.sw_dp import MultidropSwDp

swd.Interface.targetsel_db._register([PartId(9, 0x13, 0x1002, 0xf)], "RP2040")

@swd.Interface.multidrop_db.register(PartId(9, 0x13, 0x0212))
class Rp2040RescueDp(MultidropSwDp):
    target_id = 0
    max_freq = 25e6

    def __init__(self, port, targetsel):
        super().__init__(port, targetsel, name = "RP2040-RescueDp")

    def start(self):
        rd = self.port.cmd_read(0, 1)
        self.execute([self.port.cmd_write(0, 2, 0),
                      self.port.cmd_write(0, 1, 0x10000000),
                      self.port.cmd_run(32),
                      rd,
                      self.port.cmd_run(32),
                      self.port.cmd_write(0, 1, 0),
                      self.port.cmd_run(32),
        ])
        self.logger.debug("Ctrlstat: %08x", rd.data)

        for idx, core in enumerate([
                PartId(9, 0x13, 0x1002, 0),
                PartId(9, 0x13, 0x1002, 1),
        ]):
            self.port.multidrop_probe(core, reinit = not idx)

