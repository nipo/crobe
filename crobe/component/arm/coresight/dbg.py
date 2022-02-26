from .model import CoresightComponent
from ....part_id import PartId

@CoresightComponent.db.register(
    0x15, # a9 dbg
    )
class Dbg(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base, "Debug Management")

        self.cpu_name = "Cortex-A9"

        self.__cpuid_read()

        self.logger.note("PFR: %s", ', '.join(["0x%08x" % x for x in self.pfr]))
        self.logger.note("DFR: 0x%08x", self.dfr)
        self.logger.note("AFR: 0x%08x", self.afr)
        self.logger.note("MMFR: %s", ', '.join(["0x%08x" % x for x in self.mmfr]))
        self.logger.note("ISAR: %s", ', '.join(["0x%08x" % x for x in self.isar]))
        self.logger.note("DEVID: 0x%08x", self.devid)
        self.logger.note("DIDR: 0x%08x", self.didr)

    def __cpuid_read(self):
        cmds = []
        cmds += [self.cmd_reg_read(self.ID_PFR(i)) for i in range(2)]
        cmds += [self.cmd_reg_read(self.ID_DFR)]
        cmds += [self.cmd_reg_read(self.ID_AFR)]
        cmds += [self.cmd_reg_read(self.ID_MMFR(i)) for i in range(4)]
        cmds += [self.cmd_reg_read(self.ID_ISAR(i)) for i in range(6)]
        cmds += [self.cmd_reg_read(self.DEVID)]
        cmds += [self.cmd_reg_read(self.DIDR)]
        self.bus.execute(cmds)

        self.pfr = [op.data for op in cmds[0:2]]
        self.dfr = cmds[2].data
        self.afr = cmds[3].data
        self.mmfr = [op.data for op in cmds[4:8]]
        self.isar = [op.data for op in cmds[8:14]]
        self.mvfr = [0] * 3
        self.clidr = 0
        self.ccsidr = 0
        self.devid = cmds[14].data
        self.didr = cmds[15].data

    # Processor Feature Registers
    ID_PFR = staticmethod(lambda x: 0xd20 + 4 * x)
    ID_DFR = 0xd28
    ID_AFR = 0xd2c
    # Memory Model Feature Registers
    ID_MMFR = staticmethod(lambda x: 0xd30 + 4 * x)
    # Instruction Set Attribute Registers
    ID_ISAR = staticmethod(lambda x: 0xd40 + 4 * x)
    # Instruction Set Attribute Registers
    CLIDR   = 0xd78
    CTR     = 0xd7c
    CCSIDR  = 0xd80
    CSSELR  = 0xd84

    # Debug Identification Registers
    DEVID = 0xFC8
    DEVID1 = 0xFC4
    DEVID2 = 0xFC0
    DIDR = 0x000

    # Debug Control and Status Registers
    DRCR = 0x090
    DSCR = 0x088
    EACR = 0x094
    PRCR = 0x310
    PRSR = 0x314
    WFAR = 0x018

    # Software Debug Event Registers
    BCR = staticmethod(lambda x: 0x140 + 4 * x)
    BVR = staticmethod(lambda x: 0x100 + 4 * x)
    VCR = 0x01C
    WCR = staticmethod(lambda x: 0x1c0 + 4 * x)
    WVR = staticmethod(lambda x: 0x180 + 4 * x)
    BXVR = staticmethod(lambda x: 0x240 + 4 * x)
