from ...part_id import PartId
from ...protocol import jtag
from ...bitfield import *
from . import series7

parts = {
    0x04711093: "XCZU2",
    0x04710093: "XCZU3",
    0x04721093: "XCZU4",
    0x04720093: "XCZU5",
    0x04739093: "XCZU6",
    0x04730093: "XCZU7",
    0x04738093: "XCZU9",
    0x04740093: "XCZU11",
}

class ZupPsTap(jtag.Tap):
    irlen = 12
    max_freq = 30e6

    class ControllerStatus(Bitfield):
        all = Field(0, 32)
        ps_version = Field(28, 4)
        pl_fabric_pipe = Field(24, 4)
        pstp_ctrl = Field(20, 4)
        dft_mode = BooleanField(19)
        boot_mode = MappingField(14, 4, ["JTAG", "QSPI24", "QSPI32", "SD0",
                                         "NAND", "SD1", "eMMC", "USB0",
                                         "PJTAG0", "PJTAG1", "Res10", "Res11",
                                         "Res12", "Res13", "SD1 LS", "Res15"])
        cbr_done = BooleanField(13)
        scal_clear_failed = BooleanField(12)
        lbist_failed = BooleanField(11)
        bisr_failed = BooleanField(10)
        pl_pwr_sts = BooleanField(9)
        fuse_mdm_dis = BooleanField(8)
        ddr_phy_sec_gate = BooleanField(7)
        pmu_mdm_sec_gate = BooleanField(6)
        pl_tap_sec_gate = BooleanField(5)
        arm_dap_sec_gate = BooleanField(4)
        arm_dap = BooleanField(3)
        pl_tap = BooleanField(2)

    DEVICE_ID = jtag.Dr(32)
    JTAG_CTRL_REG = jtag.Dr(32)
    ERROR_STATUS_REG = jtag.Dr(121)
    JTAG_STATUS_REG = jtag.Dr(32, ControllerStatus)
    JSTATUS_REG = jtag.Dr(52)
    IP_DISABLE_REG = jtag.Dr(32)

    PMU_MDM      = jtag.Instruction(0x03, None)
    USERCODE     = jtag.Instruction(0x08, "DEVICE_ID")
    IDCODE       = jtag.Instruction(0x09, "DEVICE_ID")
    HIGHZ        = jtag.Instruction(0x0a, "BYPASS_REG")
    IP_DISABLE   = jtag.Instruction(0x19, "IP_DISABLE_REG")
    JTAG_STATUS  = jtag.Instruction(0x1f, "JTAG_STATUS_REG")
    JTAG_CTRL    = jtag.Instruction(0x20, "JTAG_CTRL_REG")
    EXTEST       = jtag.Instruction(0x26, None)
    ERROR_STATUS = jtag.Instruction(0x3e, "ERROR_STATUS_REG")

    ## Undoc
    JTAG_STATUS1 = jtag.Instruction(0x0d, "JTAG_STATUS_REG")

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        self.name = parts[int(idcode.drop_revision())] + "-PSTap"
        for instruction in self.instructions():
            instruction.ir = (instruction.ir << 6) | 0x3f

    def start(self):
        self.logger.trace("Enabling all three taps")
        self.JTAG_CTRL.shift(3)
        self.logger.debug("Controller status: %s", self.JTAG_STATUS.shift(read_tdo = True))
        super().start()

class ZupPlTap(series7.Series7):
    irlen = 12
    max_freq = 66e6

    def __init__(self, port, idcode):
        series7.Series7.__init__(self, port, idcode)
        self.name = parts[int(idcode.drop_revision())] + "-PLTap"
        for instruction in self.instructions():
            if instruction.dr and instruction.dr.name in ["BOUNDARY", "BYPASS_REG"]:
                instruction.ir |= (0x3f << 6)
            else:
                instruction.ir |= (0x24 << 6)

    def start(self):
        super().start()

@jtag.Chain.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
def zup_meta(port, idcode):
    return [ZupPlTap(port, idcode), ZupPsTap(port, idcode)]
zup_meta.irlen = 12
