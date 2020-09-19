from ...part_id import PartId
from ...protocol import jtag

@jtag.Tap.db.register(PartId(0, 0x34, 0x7926))
class FX3(jtag.Tap):
    irlen = 4
    max_freq = 25e6

    ARM_IDCODE  = jtag.Dr(32)
    SCAN_PATH_SEL = jtag.Dr(5)
    DEBUG_CHAIN = jtag.Dr(67)
    EMBEDDEDICE_CHAIN = jtag.Dr(38)

    IDCODE_ = jtag.Instruction(0xe, "DEVICE_ID")
    SCAN_N = jtag.Instruction(0x2, "SCAN_PATH_SEL")
    DEBUG = jtag.Instruction(0xc, "DEBUG_CHAIN")
    EMBEDDEDICE = jtag.Instruction(0xc, "EMBEDDEDICE_CHAIN")
    
    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "FX3"

    def embedded_ice_read(self, reg):
        cmds = [
            self.SCAN_N.cmd(2, read_tdo = False),
            self.cmd_run(1),
            self.EMBEDDEDICE.cmd((1 << 37) | (reg << 32), read_tdo = False),
            self.cmd_run(1),
            self.EMBEDDEDICE.cmd((1 << 37) | (reg << 32), read_tdo = True),
            ]
        self.execute(cmds)
        return cmds[-1].tdo & 0xffffffff
        
    def start(self):
        for i in range(32):
            self.logger.info("eice %d 0x%08x", i, self.embedded_ice_read(i))
