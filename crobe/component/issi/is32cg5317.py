from ...part_id import PartId
from ...protocol import jtag

@jtag.Chain.db.register(PartId(0xb, 0x65, 0x5317))
class CG5317(jtag.Tap):
    max_freq = 25e6

    irlen = 4

    BOUNDARY = jtag.Dr(61)

    IDCODE  = jtag.Instruction(2, "DEVICE_ID")
    SAMPLE  = jtag.Instruction(5, "BOUNDARY")
    SCAN2   = jtag.Instruction(7, "BOUNDARY")
    EXTEST   = jtag.Instruction(8, "BOUNDARY")
    SCAN4   = jtag.Instruction(13, "BOUNDARY")

    UNK_DR = jtag.Dr(3)
    UNK1    = jtag.Instruction(11, "UNK_DR")

    # Register 14 is not getting to TDO
    
    def __init__(self, port, idcode):
        super().__init__(port, idcode, "CG5317")
