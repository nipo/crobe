from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
import enum

class StUsb4500Register(enum.IntEnum):
    PasswordReg = 0x95
    Ctrl0       = 0x96
    Ctrl1       = 0x97
    RwBuffer    = 0x53

FTP_CUST_PASSWORD     = 0x47

class Ctrl0(enum.IntFlag):
    PWR          = 0x80 
    RST_N        = 0x40
    REQ          = 0x10
    SECT         = 0x07

class Ctrl1Op(enum.IntEnum):
    READ             = 0x00
    WRITE_PL         = 0x01
    WRITE_SER        = 0x02
    READ_PL          = 0x03
    READ_SER         = 0x04
    ERASE_SECTOR     = 0x05
    PROG_SECTOR      = 0x06
    SOFT_PROG_SECTOR = 0x07

class Ctrl1Sector(enum.IntFlag):
    SECTOR_0 = 0x01 << 3
    SECTOR_1 = 0x02 << 3
    SECTOR_2 = 0x04 << 3
    SECTOR_3 = 0x08 << 3
    SECTOR_4 = 0x10 << 3

class Bank0(Bitfield):
    all = Field(0, 64)
    VendorId = Field(0, 16)
    ProductId = Field(16, 16)
    BcdDevice = Field(32, 16)
    PortRoleCtrl = Field(48, 8)
    DevicePowerRoleCtrl = Field(56, 8)

class Bank1(Bitfield):
    all = Field(0, 64)
    GpioCfg = Field(2, 2)
    BusDchrg = BooleanField(13)
    R1 = BooleanField(14)
    R0 = BooleanField(15)
    VbusDischTimeToPdo = Field(16, 4)
    DischTimeTo0V = Field(20, 4)

class Bank2(Bitfield):
    all = Field(0, 64)

class Bank3(Bitfield):
    all = Field(0, 64)
    UsbCommCapable = BooleanField(16)
    PdmSinkPdoNumb = Field(17, 2)
    SinkUnconsPower = BooleanField(18)
    LutSinkPdo1 = Field(20, 4)
    SinkLL1 = Field(24, 4)
    SinkHL1 = Field(28, 4)
    LutSinkPdo2 = Field(32, 4)
    SinkLL2 = Field(36, 4)
    SinkHL2 = Field(40, 4)
    LutSinkPdo3 = Field(44, 4)
    SinkLL3 = Field(48, 4)
    SinkHL3 = Field(52, 4)

class Bank4(Bitfield):
    all = Field(0, 64)
    SinkPdoFlex1V = Field(6, 10)
    SinkPdoFlex2V = Field(16, 10)
    SinkPdoFlexI = Field(26, 10)
    PowerOkCfg = Field(37, 2)
    ReqSrcCurrent = BooleanField(52)
    AlertStatus1Mask = Field(56, 8)
    
@i2c.Interface.db.register("stusb4500")
class StUsb4500(i2c.Slave):
    def __init__(self, bus, saddr = 0x32):
        super().__init__(bus, "stusb4500", saddr)
        self.saddr = saddr

    def write(self, addr, data):
        #self.logger.debug("%s < %s", addr.name, data.hex())
        super().write(bytes([addr]) + data)

    def read(self, addr, size):
        r = super().write_read(bytes([addr]), size)
        #self.logger.debug("%s > %s", addr.name, r.hex())
        return r

    def ftp_password(self, value = 0):
        self.write(StUsb4500Register.PasswordReg, bytes([value]))

    def ftp_ctrl0(self, value = 0):
        self.logger.debug("Ctrl0 < %s", repr(value))
        self.write(StUsb4500Register.Ctrl0, bytes([value]))

    def ftp_buffer_write(self, data):
        self.logger.debug("Buffer < %s", data.hex())
        self.write(StUsb4500Register.RwBuffer, data)

    def ftp_buffer_read(self):
        r = self.read(StUsb4500Register.RwBuffer, 8)
        self.logger.debug("Buffer > %s", r.hex())
        return r

    def ftp_ctrl0_get(self):
        r = self.read(StUsb4500Register.Ctrl0, 1)
        c = Ctrl0(r[0])
        self.logger.debug("Ctrl0 > %s", repr(c))
        return c

    def ftp_ctrl0_wait(self, to_clear = 0):
        while self.ftp_ctrl0_get() & to_clear:
            pass 

    def ftp_ctrl1(self, op, sector = 0):
        self.logger.debug("Ctrl1 < %s %s", repr(op), repr(sector))
        self.write(StUsb4500Register.Ctrl1, bytes([int(op) | int(sector)]))

    def ftp_cmd_exec(self, op, ctrl0_sector = 0, ctrl1_sector = 0):
        self.ftp_ctrl1(op, ctrl1_sector)
        self.ftp_ctrl0((Ctrl0.PWR | Ctrl0.RST_N | Ctrl0.REQ) | (ctrl0_sector & Ctrl0.SECT))
        self.ftp_ctrl0_wait(Ctrl0.REQ)
        
    def cust_read_mode_enter(self):
        self.ftp_password(FTP_CUST_PASSWORD)
        self.ftp_ctrl0(Ctrl0.PWR | Ctrl0.RST_N)
        self.ftp_ctrl0()

    def cust_write_mode_enter(self, erase_map = 0x1f):
        self.ftp_password(FTP_CUST_PASSWORD)
        self.ftp_buffer_write(b"\x00" * 8)
        self.ftp_ctrl0(0)
        self.ftp_ctrl0(Ctrl0.PWR | Ctrl0.RST_N)

        erase_map &= 0x1f
        self.ftp_cmd_exec(Ctrl1Op.WRITE_SER, 0, Ctrl1Sector(erase_map << 3))
        self.ftp_cmd_exec(Ctrl1Op.SOFT_PROG_SECTOR)
        self.ftp_cmd_exec(Ctrl1Op.ERASE_SECTOR)

    def cust_test_mode_exit(self):
        self.ftp_ctrl0(Ctrl0.RST_N)
        self.ftp_ctrl1(0)
        self.ftp_password(0)

    def cust_sector_read(self, sector):
        self.ftp_ctrl0(Ctrl0.PWR | Ctrl0.RST_N)
        self.ftp_cmd_exec(Ctrl1Op.READ, sector)
        r = self.ftp_buffer_read()
        self.ftp_ctrl0()
        return r

    def cust_sector_write(self, sector, data):
        self.ftp_buffer_write(data)
        self.ftp_ctrl0(Ctrl0.PWR | Ctrl0.RST_N)
        self.ftp_cmd_exec(Ctrl1Op.WRITE_PL)
        self.ftp_cmd_exec(Ctrl1Op.PROG_SECTOR, sector)

    def customization_dump(self):
        self.cust_read_mode_enter()
        for i, bf in enumerate([Bank0, Bank1, Bank2, Bank3, Bank4]):
            data = self.cust_sector_read(i)
            v = int.from_bytes(data, "little")
            print(f"Bank{i}:")
            bf(all = v).dump_pretty(print)
        self.cust_test_mode_exit()

    def customization_set(self, sector_data):
        self.cust_write_mode_enter()
        for i, data in enumerate(sector_data):
            self.cust_sector_write(i, data)
        self.cust_test_mode_exit()
