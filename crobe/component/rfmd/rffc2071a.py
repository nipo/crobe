from ...model import PortComponent
from ...protocol import spi
import enum
import time

class Register(enum.IntEnum):
    LF = 0x00
    XO = 0x01
    CAL_TIME = 0x02
    VCO_CTRL = 0x03
    CT_CAL1 = 0x04
    CT_CAL2 = 0x05
    PLL_CAL1 = 0x06
    PLL_CAL2 = 0x07
    VCO_AUTO = 0x08
    PLL_CTRL = 0x09
    PLL_BIAS = 0x0A
    MIX_CONT = 0x0B
    P1_FREQ1 = 0x0C
    P1_FREQ2 = 0x0D
    P1_FREQ3 = 0x0E
    P2_FREQ1 = 0x0F
    P2_FREQ2 = 0x10
    P2_FREQ3 = 0x11
    FN_CTRL = 0x12
    EXT_MOD = 0x13
    FMOD = 0x14
    SDI_CTRL = 0x15
    GPO = 0x16
    T_VCO = 0x17
    IQMOD1 = 0x18
    IQMOD2 = 0x19
    IQMOD3 = 0x1A
    IQMOD4 = 0x1B
    T_CTRL = 0x1C
    DEV_CTRL = 0x1D
    TEST = 0x1E
    READBACK = 0x1f

@spi.Target.db.register("rffc2071a")
class Rffc2071a(PortComponent):
    freq = 1e4

    def __init__(self, port):
        super().__init__(port, "rffc2071a")
        self.four_wire_spi = True
        self.do_reset = False

    def option_set(self, opt):
        if opt == "spi3":
            self.four_wire_spi = False
            return
        if opt == "reset":
            self.do_reset = True
            return
        super().option_set(opt)

    def reg_read(self, reg):
        target = self.port
        spi = target.port

        c = (0x80 | int(reg)) << 16
        c |= 0xffff
        c <<= 7
        cmd = spi.cmd_shift(c.to_bytes(4, "big"), read_miso = True)

        spi.freq_cap(self.name, self.freq)
        spi.execute([
            spi.cmd_shift(b"\x00"),
            spi.cmd_cs(target.cs, mode = 0),
            cmd,
            spi.cmd_cs(None, mode = 0),
        ])
        spi.freq_cap(self.name, None)

        return (int.from_bytes(cmd.miso, "big") >> 5) & 0xffff

    def reg_write(self, reg, data):
        target = self.port
        spi = target.port

        if int(reg) == int(Register.SDI_CTRL):
            if self.four_wire_spi:
                data = int(data) | 0x1000
            else:
                data = int(data) & ~0x1000
        
        c = (int(reg) << 16) | int(data)
        c <<= 7
        cmd = spi.cmd_shift(c.to_bytes(4, "big"), read_miso = False)

        spi.freq_cap(self.name, self.freq)
        spi.execute([
            spi.cmd_shift(b"\x00"),
            spi.cmd_cs(target.cs, mode = 0),
            cmd,
            spi.cmd_cs(None, mode = 0),
        ])
        spi.freq_cap(self.name, None)

    def reg_mod(self, addr, mask, value):
        old = self.reg_read(addr)
        new = (old & ~mask) | (value & mask)
        self.reg_write(addr, new)
        
    def start(self):
        self.reg_write(Register.DEV_CTRL, 0)
        if self.do_reset:
            self.reg_write(Register.SDI_CTRL, 0x1)
            time.sleep(.01)
            self.reg_write(Register.SDI_CTRL, 0)

        if self.four_wire_spi:
            self.reg_write(Register.SDI_CTRL, 0x1000)
            self.reg_write(Register.GPO, 0x0)
        else:
            self.reg_write(Register.SDI_CTRL, 0x0)

        self.reg_write(Register.DEV_CTRL, 0x0)
        devid = self.reg_read(Register.READBACK)

        self.logger.note("Rffc2071a devid 0x%04x", devid);
