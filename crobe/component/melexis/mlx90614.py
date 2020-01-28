from crobe.model import PortComponent
from ...protocol import smbus
import struct
import time

@smbus.Interface.db.register("mlx90614")
class Mlx90614(smbus.Slave):
    def __init__(self, bus, saddr = 0x5a):
        PortComponent.__init__(self, bus, "MLX90614", saddr)

    def start(self):
        PortComponent.start(self)

        self.port.port.freq_cap(self.name, 100e3)

        idr = 0
        for i in range(4):
            idr |= self.port.read_word(self.saddr, self.REG_ID0 + i) << (i * 16)
        self.idr = idr
        self.logger.info("IDR: %x" % idr)
        self.config = self.port.read_word(self.saddr, self.REG_CONFIG1)
        self.dual = bool(self.config & self.CONFIG1_IR_DUAL)

    def address_change(self, next_addr):
        self.write_word(self.REG_SMBUS_ADDRESS, 0)
        time.sleep(.1)
        self.write_word(self.REG_SMBUS_ADDRESS, next_addr)
        time.sleep(.1)
        
    def sensors_read(self):
        regs = {
            "Ta": self.REG_TA,
            "Tobj1": self.REG_TOBJ1,
        }
        if self.dual:
            regs["Tobj2"] = self.REG_TOBJ2

        values = {}
        for name, addr in regs.items():
            values[name] = (self.read_word(addr) & 0x7fff) / 50.
        return values

    REG_TA             = 0x06
    REG_TOBJ1          = 0x07
    REG_TOBJ2          = 0x08
    REG_TOMAX          = 0x20
    REG_TOMIN          = 0x21
    REG_PWMCTRL        = 0x22
    REG_TA_RANGE       = 0x23
    REG_KE             = 0x24
    REG_CONFIG1        = 0x25
    REG_SMBUS_ADDRESS  = 0x2e
    REG_ID0            = 0x3c
    REG_ID1            = 0x3d
    REG_ID2            = 0x3e
    REG_ID3            = 0x3f
    REG_FLAGS          = 0xf0
    CMD_SLEEP          = 0xff

    CONFIG1_IIR_0_5         = 0x0000
    CONFIG1_IIR_0_571       = 0x0007
    CONFIG1_IIR_0_666       = 0x0006
    CONFIG1_IIR_0_8         = 0x0005
    CONFIG1_IIR_1           = 0x0004
    CONFIG1_AMB_PTC         = 0x0008
    CONFIG1_PWM_TA_IR1      = 0x0000
    CONFIG1_PWM_TA_IR2      = 0x0010
    CONFIG1_PWM_IR1_IR1     = 0x0020
    CONFIG1_PWM_IR2         = 0x0030
    CONFIG1_IR_DUAL         = 0x0040
    CONFIG1_KS              = 0x0080
    CONFIG1_FIR_N_LOG2 = staticmethod(lambda x: ((x - 3) & 0x7) << 8)
    CONFIG1_AMP_GAIN_1      = 0x0000
    CONFIG1_AMP_GAIN_3      = 0x0800
    CONFIG1_AMP_GAIN_6      = 0x1000
    CONFIG1_AMP_GAIN_12_5   = 0x1800
    CONFIG1_AMP_GAIN_25     = 0x2000
    CONFIG1_AMP_GAIN_50     = 0x2800
    CONFIG1_AMP_GAIN_100    = 0x3000
    CONFIG1_THERMOCOMP_NEG  = 0x8000
