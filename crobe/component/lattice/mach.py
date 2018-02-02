from ...part_id import PartId
from ...adapter.protocol import jtag
import struct
from ... import bitstring
import datetime

parts = {
    0x012ba043: "MachXO2",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class MachXO2(jtag.Tap):
    irlen = 8

    IR_IDCODE               = 0b11100000
    IR_ISC_ENABLE           = 0b11000110
    IR_ISC_PROGRAM_DONE     = 0b01011110
    IR_LSC_PROGRAM_SECPLUS  = 0b11001111
    IR_ISC_PROGRAM_USERCODE = 0b11000010
    IR_ISC_PROGRAM_SECURITY = 0b11001110
    IR_ISC_PROGRAM          = 0b01100111
    IR_LSC_ENABLE_X         = 0b01110100
    IR_BYPASS               = 0b11111111
    IR_ISC_DATA_SHIFT       = 0b00001010
    IR_ISC_DISCHARGE        = 0b00010100
    IR_USERCODE             = 0b11000000
    IR_ISC_ERASE_DONE       = 0b00100100
    IR_CLAMP                = 0b01111000
    IR_ISC_ADDRESS_SHIFT    = 0b01000010
    IR_PRELOAD              = 0b00011100
    IR_ISC_READ             = 0b10000000
    IR_ISC_DISABLE          = 0b00100110
    IR_ISC_ERASE            = 0b00001110
    IR_ISC_NOOP             = 0b00110000
    IR_SAMPLE               = 0b00011100
    IR_HIGHZ                = 0b00011000
    IR_EXTEST               = 0b00010101

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = parts.get(int(port.idcode_at(index).drop_revision()), "MachXO2")
