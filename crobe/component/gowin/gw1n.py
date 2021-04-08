from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ...util.endian import bitswap8
import time

parts = {
    0x0000: "GW2A[R]-18/18C",
    0x0002: "GW2A-55/55C",
    0x1001: "GW1N[R]-4",
    0x1003: "GW1N[R]-4[BC]",
    0x1005: "GW1N[R]-9[C]",
    0x1006: "GW1NZ-1",
    0x1009: "GW1NS[ER]-4C",
    0x3000: "GW1NS-2",
    0x3001: "GW1NS[RE]-2C",
    0x9002: "GW1N-1",
    0x9003: "GW1N-1S",
}

# Reference: UG290-2.3E
# https://www.gowinsemi.com/upload/database_doc/1130/document/6020e45f5fe13.pdf
@jtag.Chain.db.register(*set([PartId(8, 0x0d, p) for p in parts.keys()]))
class GowinFpga(jtag.Tap):
    irlen = 8
    max_freq = 25e6

    BOUNDARY      = jtag.Dr(232)
    ISC_DEFAULT   = jtag.Dr(1)
    ISC_PDATA     = jtag.Dr(None)

    ISC_DISABLE          = jtag.Instruction(0x3a, "ISC_DEFAULT")
    ISC_NOOP             = jtag.Instruction(0x02, "ISC_DEFAULT")
    ISC_PROGRAM_SECURITY = jtag.Instruction(0x0b, "ISC_DEFAULT")
    ISC_SRAM_ERASE       = jtag.Instruction(0x05, "ISC_DEFAULT")
    ISC_SRAM_ERASE_DONE  = jtag.Instruction(0x09, "ISC_DEFAULT")
    ISC_EFLASH_ERASE     = jtag.Instruction(0x75, "ISC_DEFAULT")
    ISC_SRAM_ERASE_DONE  = jtag.Instruction(0x09, "ISC_DEFAULT")
    ISC_ENABLE           = jtag.Instruction(0x15, "ISC_DEFAULT")
    ISC_PROGRAM_DONE     = jtag.Instruction(0x08, "ISC_DEFAULT")

    ISC_ADDRESS_INIT     = jtag.Instruction(0x12, "ISC_DEFAULT")
    ISC_TRANSFER_CONFIG  = jtag.Instruction(0x17, "ISC_DEFAULT")

    HIGHZ                = jtag.Instruction(0x0c, "TAP_BYPASS")
    CLAMP                = jtag.Instruction(0x07, "TAP_BYPASS")

    IDCODE               = jtag.Instruction(0x11, "DEVICE_ID")
    IDCODE_PRIV          = jtag.Instruction(0x19, "DEVICE_ID")
    ISC_PROGRAM_USERCODE = jtag.Instruction(0x0a, "DEVICE_ID")
    USERCODE             = jtag.Instruction(0x13, "DEVICE_ID")

    ISC_READ             = jtag.Instruction(0x03, "ISC_PDATA")
    ISC_PROGRAM          = jtag.Instruction(0x14, "ISC_PDATA")

    PRELOAD              = jtag.Instruction(0x01, "BOUNDARY")
    SAMPLE               = jtag.Instruction(0x01, "BOUNDARY")
    EXTEST               = jtag.Instruction(0x04, "BOUNDARY")
    
    def __init__(self, port, index, idcode):
        super().__init__(port, index, idcode)
        self.name = parts[idcode.part_no]
