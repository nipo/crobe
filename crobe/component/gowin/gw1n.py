from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ... import bitstring
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
    0x1206: "GW1-2[B]/1P5",
}

# Reference: UG290-2.3E
# https://www.gowinsemi.com/upload/database_doc/1130/document/6020e45f5fe13.pdf
class GowinFpga(jtag.Tap):
    irlen = 8

    BOUNDARY        = jtag.Dr(None)
    ISC_DEFAULT     = jtag.Dr(1)
    ISC_PDATA       = jtag.Dr(None)
    STATUS_REGISTER = jtag.Dr(32)

    ISC_DISABLE          = jtag.Instruction(0x3a, "ISC_DEFAULT")
    ISC_NOOP             = jtag.Instruction(0x02, "ISC_DEFAULT")
    ISC_PROGRAM_SECURITY = jtag.Instruction(0x0b, "ISC_DEFAULT")
    ISC_SRAM_ERASE       = jtag.Instruction(0x05, "ISC_DEFAULT")
    ISC_SRAM_ERASE_DONE  = jtag.Instruction(0x09, "ISC_DEFAULT")
    ISC_EFLASH_ERASE     = jtag.Instruction(0x75, "STATUS_REGISTER")
    ISC_ENABLE           = jtag.Instruction(0x15, "ISC_DEFAULT")
    ISC_PROGRAM_DONE     = jtag.Instruction(0x08, "ISC_DEFAULT")

    ISC_ADDRESS_INIT     = jtag.Instruction(0x12, "ISC_DEFAULT")
    ISC_TRANSFER_CONFIG  = jtag.Instruction(0x17, "ISC_PDATA")

    HIGHZ                = jtag.Instruction(0x0c, "TAP_BYPASS")
    CLAMP                = jtag.Instruction(0x07, "TAP_BYPASS")

    IDCODE               = jtag.Instruction(0x11, "DEVICE_ID")
    IDCODE_PRIV          = jtag.Instruction(0x19, "DEVICE_ID")
    ISC_PROGRAM_USERCODE = jtag.Instruction(0x0a, "DEVICE_ID")
    USERCODE             = jtag.Instruction(0x13, "DEVICE_ID")

    ISC_READ             = jtag.Instruction(0x03, "ISC_PDATA")
    ISC_PROGRAM          = jtag.Instruction(0x14, "ISC_PDATA")

    READ_STATUS          = jtag.Instruction(0x41, "STATUS_REGISTER")

    PRELOAD              = jtag.Instruction(0x01, "BOUNDARY")
    SAMPLE               = jtag.Instruction(0x01, "BOUNDARY")
    EXTEST               = jtag.Instruction(0x04, "BOUNDARY")
    
    def __init__(self, port, index, idcode):
        super().__init__(port, index, idcode)
        self.name = parts[idcode.part_no]

    def start(self):
        super().start()
        self.logger.info("IR status: %x", self.ir_status_read())
        self.logger.info("Status: %x", self.READ_STATUS.shift(read_tdo = True))

    def sram_erase(self):
        raise NotImplementedError()

    def flash_erase(self):
        raise NotImplementedError()

    def sram_configure(self, program_data):
        raise NotImplementedError()

    def load(self, program):
        self.sram_erase()
        data = program[0].data
        self.sram_configure(data)
        self.logger.info(self.status_read())

    def stop(self):
        self.sram_erase()
        self.logger.info(self.status_read())

    def reset(self):
        self.logger.warning("Not implemented")

    def status_read(self):
        c = self.READ_STATUS.cmd(0)
        self.execute([c])
        return self.Status(all = int(c.tdo))

    def sram_erase(self):
        self.logger.info("Erasing SRAM")
        self.execute([
            self.ISC_ENABLE.cmd(),
            self.cmd_run(8),
            self.ISC_SRAM_ERASE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(2),
            ])
        time.sleep(.01)
        self.execute([
            self.ISC_SRAM_ERASE_DONE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(8),
            self.ISC_DISABLE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(8),
            self.cmd_run(8),
            ])

    def sram_configure(self, program_data):
        self.logger.info("Loading %d bytes to SRAM", len(program_data))
        program_data = bitswap8(program_data)
        program_data = b'\xff'*60 + program_data + b'\xff'*60
        self.execute([
            self.ISC_ENABLE.cmd(),
            self.cmd_run(2),
            self.ISC_ADDRESS_INIT.cmd(),
            self.ISC_TRANSFER_CONFIG.cmd(),
            self.cmd_run(2),
            self.ISC_TRANSFER_CONFIG.cmd(bitstring.BitString(program_data)),
            self.ISC_DISABLE.cmd(),
            self.cmd_run(2),
            self.ISC_NOOP.cmd(),
            self.cmd_run(5),
            ])
        
@jtag.Chain.db.register(*set([PartId(8, 0x0d, p) for (p,n) in parts.items() if n.startswith("GW1")]))
class Gw1(GowinFpga):
    max_freq = 10e6

    class Status(bitfield.Bitfield):
        all          = bitfield.Field(0, 32)
        CRCError     = bitfield.BooleanField(0)
        BadCommand   = bitfield.BooleanField(1)
        IdError      = bitfield.BooleanField(2)
        Timeout      = bitfield.BooleanField(3)
        Vld          = bitfield.BooleanField(12)
        Done         = bitfield.BooleanField(13)
        Security     = bitfield.BooleanField(14)
        Ready        = bitfield.BooleanField(15)

    def flash_erase(self):
        raise NotImplementedError()

@jtag.Chain.db.register(*set([PartId(8, 0x0d, p) for (p,n) in parts.items() if n.startswith("GW2A")]))
class Gw2a(GowinFpga):
    max_freq = 30e6

    class Status(bitfield.Bitfield):
        all          = bitfield.Field(0, 32)
        CRCError     = bitfield.BooleanField(0)
        BadCommand   = bitfield.BooleanField(1)
        IdError      = bitfield.BooleanField(2)
        Timeout      = bitfield.BooleanField(3)
        Vld          = bitfield.BooleanField(12)
        Done         = bitfield.BooleanField(13)
        Security     = bitfield.BooleanField(14)
        Encrypted    = bitfield.BooleanField(15)
        KeyOk        = bitfield.BooleanField(16)

    def flash_erase(self):
        self.logger.info("Erasing flash")
        self.execute([
            self.ISC_ENABLE.cmd(),
            self.cmd_run(10),
            self.ISC_EFLASH_ERASE.cmd(),
            self.cmd_run(1),
            self.ISC_EFLASH_ERASE.cmd(0),
            self.cmd_run(10000),
            self.ISC_DISABLE.cmd(),
            self.cmd_run(2),
            self.ISC_NOOP.cmd(),
            self.cmd_run(5),
            ])
