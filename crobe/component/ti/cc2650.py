from .icepick import *
from ...part_id import PartId
from ...protocol import jtag

class DebugTap(jtag.Tap):
    def dr_lengths_discover(self):
        ir_lengths = self.dr_discover_all()
        for k, v in ir_lengths.items():
            self.logger.note("IR %02x, drlen %d", k, v)
            if v == 32:
                code = self.dr_shift(k, 0, 32, read_tdo = True)
                self.logger.note(" -> read value: %08x", code)

    def start(self):
        super().start()
        self.dr_lengths_discover()
                
# Test Tap #0
@jtag.Chain.db.register("cc2650-dft")
class DftTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "Ti CC2650 DFT"

    def start(self):
        dr6 = self.dr_discover(0x6)
        assert len(dr6) == 78
        
    # IR 00, drlen 1
    # IR 06, drlen 78
    # IR 07, drlen 20
    # IR 08, drlen 32
    #  -> read value: 00000000
    # IR 09, drlen 28
    # IR 0b, drlen 12
    # IR 0f, drlen 1

    PROFILE_REG = jtag.Dr(78)
    PROFILE = jtag.Instruction(6, "PROFILE_REG")

# Test Tap #3
@jtag.Chain.db.register("cc2650-efuse")
class EfuseTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "Ti CC2650 Efuse"

    def start(self):
        dr9 = self.dr_discover(0x9)
        assert len(dr9) == 40

    # IR 00, drlen 1
    # IR 01, drlen 1
    # IR 02, drlen 1
    # IR 03, drlen 1
    # IR 04, drlen 1
    # IR 05, drlen 1
    # IR 06, drlen 1
    # IR 07, drlen 1
    # IR 08, drlen 1
    # IR 09, drlen 40
    # IR 0b, drlen 1
    # IR 0c, drlen 1
    # IR 0d, drlen 1
    # IR 0e, drlen 1
    # IR 0f, drlen 1

# Test Tap #5
@jtag.Chain.db.register("cc2650-aon")
class AonTap(jtag.Tap):
    irlen = 4

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        self.name = "Ti CC2650 AON"

    def start(self):
        drc = self.dr_discover(0xc)
        assert len(drc) == 7

    # IR 00, drlen 1
    # IR 01, drlen 8
    # IR 02, drlen 28
    # IR 03, drlen 28
    # IR 04, drlen 9
    # IR 05, drlen 9
    # IR 06, drlen 21
    # IR 07, drlen 21
    # IR 08, drlen 9
    # IR 09, drlen 9
    # IR 0a, drlen 14
    # IR 0b, drlen 14
    # IR 0c, drlen 7
    # IR 0d, drlen 5
    # IR 0f, drlen 1

@jtag.Chain.db.register(PartId(0, 0x17, 0xb99a))
class Cc2650Icepick(IcePick):
    TAPS = {
        (Block.DebugTap, 0): PartId(4, 0x3b, 0xba00),
        (Block.TestTap, 0): "cc2650-dft",
        #(Block.TestTap, 1): "cc2650-pbist",
        #(Block.TestTap, 2): "cc2650-pbist",
        (Block.TestTap, 3): "cc2650-efuse",
        #(Block.TestTap, 4): "cc2650-prcm",
        (Block.TestTap, 5): "cc2650-aon",
        }

    def start(self):
        super().start()
        self.logger.trace("Enabling DP and AON Taps")
        self.dp = self.tap_enable(Block.DebugTap, 0)
        self.aon = self.tap_enable(Block.TestTap, 5)
        #self.dft = self.tap_enable(Block.TestTap, 0)
        #self.efuse = self.tap_enable(Block.TestTap, 3)
        self.port.dump("After adding DP and AON")

    def system_reset(self):
        with self.port.port.freq_capped("icepick", 1e5):
            self.execute([
                self.ROUTER.cmd(Router(write_en = True, block = Block.IcePick, register = IcePickBlock.Control, value = 0x41)),
                self.cmd_run(1),
                self.ROUTER.cmd(Router(write_en = True, block = Block.IcePick, register = IcePickBlock.Control, value = 0x00)),
                self.cmd_run(1),
                ])
