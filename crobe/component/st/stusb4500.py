from ...model import PortComponent
from ...protocol import i2c

PASSWORD_REG_ADDR = 0x95
FTP_CUST_PASSWORD     = 0x47

CTRL_0_ADDR            = 0x96
CTRL_0_PWR          = 0x80 
CTRL_0_RST_N        = 0x40
CTRL_0_REQ          = 0x10
CTRL_0_SECT         = 0x07

CTRL_1_ADDR            = 0x97
CTRL_1_SECT_MAP          = 0xF8
CTRL_1_OPCODE       = 0x07
RW_BUFFER_ADDR             = 0x53

OP_READ             = 0x00
OP_WRITE_PL         = 0x01
OP_WRITE_SER        = 0x02
OP_READ_PL          = 0x03
OP_READ_SER         = 0x04
OP_ERASE_SECTOR     = 0x05
OP_PROG_SECTOR      = 0x06
OP_SOFT_PROG_SECTOR = 0x07
SECTOR_0 = 0x01
SECTOR_1 = 0x02
SECTOR_2 = 0x04
SECTOR_3 = 0x08
SECTOR_4 = 0x10

@i2c.Interface.db.register("stusb4500")
class StUsb4500(i2c.Slave):
    def __init__(self, bus, saddr = 0x32):
        super().__init__(bus, "stusb4500", saddr)
        self.saddr = saddr

    def write(self, addr, data):
        super().write(bytes([addr]) + data)

    def read(self, addr, size):
        return super().write_read(bytes([addr]), size)

    def ftp_password(self, value = 0):
        self.write(PASSWORD_REG_ADDR, bytes([value]))

    def ftp_ctrl0(self, value = 0):
        self.write(CTRL_0_ADDR, bytes([value]))

    def ftp_ctrl0_wait(self, to_clear = 0):
        while self.read(CTRL_0_ADDR, 1)[0] & to_clear:
            pass 

    def ftp_ctrl1(self, value = 0):
        self.write(CTRL_1_ADDR, bytes([value]))

    def ftp_cmd_exec(self, ctrl1, ctrl0_sector = 0):
        self.ftp_ctrl1(ctrl1)
        self.ftp_ctrl0((CTRL_0_PWR | CTRL_0_RST_N | CTRL_0_REQ) | (ctrl0_sector & CTRL_0_SECT))
        self.ftp_ctrl0_wait(CTRL_0_REQ)
        
    def cust_read_mode_enter(self):
        self.ftp_password(FTP_CUST_PASSWORD)
        self.ftp_ctrl0(CTRL_0_PWR | CTRL_0_RST_N)
        self.ftp_ctrl0()

    def cust_write_mode_enter(self, erase_map = 0x1f):
        self.ftp_password(FTP_CUST_PASSWORD)
        self.write(RW_BUFFER_ADDR, bytes([0]) * 8)
        self.ftp_ctrl0(0)
        self.ftp_ctrl0(CTRL_0_PWR | CTRL_0_RST_N)

        self.ftp_cmd_exec(((erase_map << 3) & CTRL_1_SECT_MAP) | OP_WRITE_SER)
        self.ftp_cmd_exec(OP_SOFT_PROG_SECTOR)
        self.ftp_cmd_exec(OP_ERASE_SECTOR)

    def cust_test_mode_exit(self):
        self.ftp_ctrl0(CTRL_0_RST_N)
        self.ftp_ctrl1(0)
        self.ftp_password(0)

    def cust_sector_read(self, sector):
        self.ftp_ctrl0(CTRL_0_PWR | CTRL_0_RST_N)
        self.ftp_cmd_exec(OP_READ, sector)
        r = self.read(RW_BUFFER_ADDR, 8)
        self.ftp_ctrl0()
        return r

    def cust_sector_write(self, sector, data):
        self.write(RW_BUFFER_ADDR, data)
        self.ftp_ctrl0(CTRL_0_PWR | CTRL_0_RST_N)
        self.ftp_cmd_exec(OP_WRITE_PL)
        self.ftp_cmd_exec(OP_PROG_SECTOR, sector)

    def customization_dump(self):
        self.cust_read_mode_enter()
        for i in range(5):
            data = self.cust_sector_read(i)
            print(f"Sector{i}: {data.hex()}")
        self.cust_test_mode_exit()

    def customization_set(self, sector_data):
        self.cust_write_mode_enter()
        for i, data in enumerate(sector_data):
            self.cust_sector_write(i, data)
        self.cust_test_mode_exit()
