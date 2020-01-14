from ...part_id import PartId
from ...protocol import jtag
import struct
from ... import bitstring

parts = {
    0x00147043: "ispPAC-POWR607",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class IspPac(jtag.Tap):
    irlen = 8
    max_freq = 25e6

    BULK_ERASE                  = 0b00000011 # Bulk erase device
    BYPASS                      = 0b11111111 # Bypass - connect TDO to TDI
    DISCHARGE                   = 0b00010100 # Fast VPP discharge
    ERASE_DONE_BIT              = 0b00100100 # Erases ‘Done’ bit only
    EXTEST                      = 0b00000000 # Bypass - connect TDO to TDI
    IDCODE                      = 0b00010110 # Read contents of manufacturer ID code (32 bits)
    OUTPUTS_HIGHZ               = 0b00011000 # Force all outputs to High-Z state, including FET driver outputs
    SAMPLE_PRELOAD              = 0b00011100 # Sample/Preload. Default to bypass.
    PROGRAM_DISABLE             = 0b00011110 # Disable program mode
    PROGRAM_DONE_BIT            = 0b00101111 # Programs the Done bit
    PROGRAM_ENABLE              = 0b00010101 # Enable program mode
    PROGRAM_SECURITY            = 0b00001001 # Program security fuse
    RESET                       = 0b00100010 # Resets device
    PLD_ADDRESS_SHIFT           = 0b00000001 # PLD_Address register (61 bits)
    PLD_DATA_SHIFT              = 0b00000010 # PLD_Data register (81 bits)
    PLD_INIT_ADDR_FOR_PROG_INCR = 0b00100001 # Initialize the address register for auto increment
    PLD_PROG_INCR               = 0b00100111 # Program column register to E2 and auto increment address register
    PLD_PROGRAM                 = 0b00000111 # Program PLD data register to E2
    PLD_VERIFY                  = 0b00001010 # Verifies PLD column data
    PLD_VERIFY_INCR             = 0b00101010 # Load column register from E2 and auto increment address register
    UES_PROGRAM                 = 0b00011010 # Program UES bits into E2
    UES_READ                    = 0b00010111 # Read contents of UES register from E2 (32 bits)

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = parts.get(int(self.idcode.drop_revision()), "ispPAC")
