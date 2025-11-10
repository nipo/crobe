from ..model import JtagSramFpga, SramFpga
from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ... import bitstring
from ...util.endian import bitswap8
import time

parts = {
    0x20f3: "LP025",
}

@jtag.Chain.db.register(PartId(0, 0x6e, 0x20f3))
class CycloneFpga(jtag.Tap, JtagSramFpga):
    irlen = 10
    
    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        JtagSramFpga.__init__(self)
        self.name = f"Cyclone10-{parts.get(idcode.part_no, hex(idcode.part_no))}"

        CONFIG = jtag.Dr(None)
        BOUNDARY = jtag.Dr(None)
        USER0            = jtag.Instruction(0x00c)
        USER1            = jtag.Instruction(0x00e)

        LOAD_SRAM        = jtag.Instruction(0x002)
        START            = jtag.Instruction(0x003)
        SCAN_CHECK       = jtag.Instruction(0x004) # This looks like another SAMPLE

        EXTEST           = jtag.Instruction(0x00f, "BOUNDARY")
        SAMPLE           = jtag.Instruction(0x005, "BOUNDARY")
        IDCODE           = jtag.Instruction(0x006, "DEVICE_ID")
        USERCODE         = jtag.Instruction(0x007, "DEVICE_ID")
        CLAMP            = jtag.Instruction(0x00a, "BOUNDARY")
        HIGHZ            = jtag.Instruction(0x00b, "BOUNDARY")
        ACTIVE_ENGAGE    = jtag.Instruction(0x2b0, "CONFIG")
        ACTIVE_DISENGAGE = jtag.Instruction(0x2d0, "CONFIG")
        CONFIG_IO        = jtag.Instruction(0x00d, "CONFIG")

    def sram_configure(self, program_data):
        self.logger.trace("Loading %d bytes to SRAM", len(program_data))
        raise NotImplementedError()
