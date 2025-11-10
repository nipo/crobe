from ..model import JtagSramFpga, SramFpga
from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ... import bitstring
from ...util.endian import bitswap8
import time

parts = {
}

@jtag.Chain.db.register(PartId(0, 0x6e, 0x20f3))
class Max10Fpga(jtag.Tap, JtagSramFpga):
    irlen = 10
    
    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        JtagSramFpga.__init__(self)
        self.name = f"Max10-{parts.get(idcode.part_no, hex(idcode.part_no))}"

        CONFIG = jtag.Dr(None)
        BOUNDARY = jtag.Dr(None)
        USER0            = jtag.Instruction(0x00c)
        USER1            = jtag.Instruction(0x00e)

        EXTEST           = jtag.Instruction(0x00f, "BOUNDARY")
        SAMPLE           = jtag.Instruction(0x005, "BOUNDARY")
        IDCODE           = jtag.Instruction(0x006, "DEVICE_ID")
        USERCODE         = jtag.Instruction(0x007, "DEVICE_ID")
        CLAMP            = jtag.Instruction(0x00a, "BOUNDARY")
        HIGHZ            = jtag.Instruction(0x00b, "BOUNDARY")

        
        ISC_ADDRESS_SHIFT = jtag.Instruction(0x203)
        ISC_READ          = jtag.Instruction(0x205)
        ISC_ENABLE        = jtag.Instruction(0x2cc)
        ISC_DISABLE       = jtag.Instruction(0x201)
        ISC_ADDRESS_SHIFT = jtag.Instruction(0x203)
        ISC_ERASE         = jtag.Instruction(0x2f2)
        ISC_PROGRAM       = jtag.Instruction(0x2f4)
        DSM_ICB_PROGRAM   = jtag.Instruction(0x3F4)
        DSM_VERIFY        = jtag.Instruction(0x307)
        DSM_CLEAR         = jtag.Instruction(0x3f2)
        
    def sram_configure(self, program_data):
        self.logger.trace("Loading %d bytes to SRAM", len(program_data))
        raise NotImplementedError()
