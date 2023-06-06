from ..model import JtagSramFpga, SramFpga
from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag, spi
from ... import bitfield
from ... import bitstring
from ...util.endian import bitswap8
import time

parts = {
    0x0000: "GW2A-18/18C",
    0x0002: "GW2A-55/55C",
    0x1001: "GW1N-4",
    0x1003: "GW1N-4[BC]",
    0x1004: "GW1N-9C",
    0x1005: "GW1N-9",
    0x1006: "GW1NZ-1",
    0x1009: "GW1NS-4C",
    0x3000: "GW1NS-2",
    0x3001: "GW1NS-2C",
    0x9002: "GW1N-1",
    0x9003: "GW1N-1S",
    0x1206: "GW1-1P5/2[B]",
}

# Reference: UG290-2.3E
# https://www.gowinsemi.com/upload/database_doc/1130/document/6020e45f5fe13.pdf
class GowinFpga(jtag.Tap, JtagSramFpga):
    irlen = 8

    USER_IR = [0x42, 0x43]

    BOUNDARY        = jtag.Dr(None)
    ISC_DEFAULT     = jtag.Dr(1)
    ISC_PDATA       = jtag.Dr(None)

    BYPASS2              = jtag.Instruction(0x00, "BYPASS_REG")

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

    HIGHZ                = jtag.Instruction(0x0c, "BYPASS_REG")
    CLAMP                = jtag.Instruction(0x07, "BYPASS_REG")

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
    UNK_06 = jtag.Instruction(0x06, 'BOUNDARY')

    # User registers
    USER1 = jtag.Instruction(0x42, None)
    USER2 = jtag.Instruction(0x43, None)
    IR_USER1 = jtag.Instruction(0x42, None)
    IR_USER2 = jtag.Instruction(0x43, None)
    
    # Documented for SPI configuration
    WRITE_DISABLE     = jtag.Instruction(0x3a, 'ISC_DEFAULT')
    WRITE_DATA        = jtag.Instruction(0x3b, None)
    RECONFIGURE       = jtag.Instruction(0x3c, 'ISC_DEFAULT')
    PROGRAM_SPI_FLASH = jtag.Instruction(0x16, 'ISC_DEFAULT')

    # 32-bit unknown IRs
    # 0x10, 0x50, 0x70, 0x71, 0x73, 0x76, 0x80
    
    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        JtagSramFpga.__init__(self)
        self.name = parts[idcode.part_no]

    def start(self):
        super().start()
        status = self.status_read()
        self.logger.debug("Status: %s", status)

    def flash_erase(self):
        raise NotImplementedError()

    def sram_configure(self, program_data):
        raise NotImplementedError()

    def load(self, program):
        self.sram_erase()
        data = program[0].data
        self.sram_configure(data)
        status = self.status_read()
        self.logger.debug("Status: %s", status)
        return status.Done

    def stop(self):
        self.sram_erase()
        self.logger.debug(self.status_read())

    def reset(self):
        self.logger.warning("Not implemented")

    def status_read(self):
        r = self.READ_STATUS.shift(read_tdo = True)
        self.logger.info("Status: %s", r)
        return r

    def _sram_erase(self):
        self.logger.trace("Erasing SRAM")
        self.execute([
            self.ISC_ENABLE.cmd(),
            self.cmd_run(8),
            self.ISC_SRAM_ERASE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(100),
        ])
        time.sleep(10e-3)
        self.execute([
            self.ISC_SRAM_ERASE_DONE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(8),
            self.ISC_DISABLE.cmd(),
            self.cmd_run(8),
            self.ISC_NOOP.cmd(),
            self.cmd_run(100),
            ])
        time.sleep(10e-3)

    def sram_erase(self):
        for retry in range(3):
            self._sram_erase()
            st = self.status_read()
            if not st.Done:
                break
        assert not st.Done, st

    def assert_done(self):
        for retry in range(3):
            r = self.READ_STATUS.cmd(read_tdo = True)
            self.execute([
                self.cmd_run(1000),
                r,
                ])
            self.logger.info("Status: %s", r)
            st = r.tdo
            if st.Done:
                break
        assert st.Done, st

    def sram_configure(self, program_data):
        self.logger.trace("Loading %d bytes to SRAM", len(program_data))
        program_data = bitswap8(program_data)
        program_data = b'\xff'*60 + program_data + b'\xff'*60
        self.execute([
            self.ISC_ENABLE.cmd(),
            self.cmd_run(100),
            self.ISC_ADDRESS_INIT.cmd(),
            self.cmd_run(100),
            self.ISC_TRANSFER_CONFIG.cmd(),
            self.cmd_run(100),
            self.ISC_TRANSFER_CONFIG.cmd(bitstring.BitString(program_data)),
            self.cmd_run(100),
            self.ISC_DISABLE.cmd(),
            self.cmd_run(100),
            self.ISC_NOOP.cmd(),
            self.cmd_run(100),
            ])
        self.assert_done()
        return self.status_read().Done
        
@jtag.Chain.db.register(*set([PartId(8, 0x0d, p) for (p,n) in parts.items() if n.startswith("GW1")]))
class Gw1n(GowinFpga):
    max_freq = 25e6

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
    STATUS_REGISTER = jtag.Dr(32, type = Status)

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
    STATUS_REGISTER = jtag.Dr(32, type = Status)

    def flash_erase(self):
        self.logger.trace("Erasing flash")
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

@GowinFpga.application_db.register("spi")
def spi_interface(tap):
    from ...loadable.object import Program
    import pkg_resources

    fw_name = f"fw/{int(tap.idcode.drop_revision()):#010x}_jtag_spi.fs.gz"
    try:
        filename = pkg_resources.resource_filename(__name__, fw_name)
    except:
        raise db.NoMatch("spi")
    tap.load(Program.from_file(filename))

    from ..jtag_spi_bridge import JtagSpiBridge
    return JtagSpiBridge(tap, tap.USER_IR[0], tap.USER_IR[1], tap.max_freq)

@spi.Target.db.register("gowin_slave")
def gowin_slave_probe(target, *args):
    return GowinSlaveSerial(target)

class GowinSlaveSerial(PortComponent, SramFpga):
    def __init__(self, port):
        PortComponent.__init__(self, port, "Slave Gowin")
        SramFpga.__init__(self)

    def start(self):
        self.port.freq_cap("gowin", 50e6)
        super().start()

    def stop(self):
        pass

    def reset(self):
        pass

    def load(self, program):
        self.port.port.reset(True)
        self.port.port.reset(False)

        blob = program[0].data
        self.logger.trace("Loading %d bytes bitstream", len(blob))
        self.port.execute([self.port.cmd_cs(True)])
        for off in range(0, len(blob), 1024):
            chunk = blob[off : off + 1024]
            self.port.execute([self.port.cmd_shift(chunk, read_miso = False)])
        self.port.execute([self.port.cmd_shift(b'\x00'*32, read_miso = False)])
        self.port.execute([self.port.cmd_cs(False)])
