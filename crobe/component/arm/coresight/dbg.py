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

        self.logger.info("PFR: %s", ', '.join(["0x%08x" % x for x in self.pfr]))
        self.logger.info("DFR: 0x%08x", self.dfr)
        self.logger.info("AFR: 0x%08x", self.afr)
        self.logger.info("MMFR: %s", ', '.join(["0x%08x" % x for x in self.mmfr]))
        self.logger.info("ISAR: %s", ', '.join(["0x%08x" % x for x in self.isar]))

    def __cpuid_read(self):
        cmds = []
        cmds += [self.cmd_reg_read(self.ID_PFR(i)) for i in range(2)]
        cmds += [self.cmd_reg_read(self.ID_DFR)]
        cmds += [self.cmd_reg_read(self.ID_AFR)]
        cmds += [self.cmd_reg_read(self.ID_MMFR(i)) for i in range(4)]
        cmds += [self.cmd_reg_read(self.ID_ISAR(i)) for i in range(5)]
        self.bus.execute(cmds)

        self.pfr = [op.data for op in cmds[0:2]]
        self.dfr = cmds[2].data
        self.afr = cmds[3].data
        self.mmfr = [op.data for op in cmds[4:8]]
        self.isar = [op.data for op in cmds[8:13]]
        self.mvfr = [0] * 3
        self.clidr = 0
        self.ccsidr = 0

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

