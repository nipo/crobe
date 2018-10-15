
class Xadc:
    XADC_REG_VALUE        = staticmethod(lambda x:x)
    XADC_REG_TEMP_MAX     = 0x20
    XADC_REG_VCCINT_MAX   = 0x21
    XADC_REG_VCCAUX_MAX   = 0x22
    XADC_REG_VCCBRAM_MAX  = 0x23
    XADC_REG_TEMP_MIN     = 0x24
    XADC_REG_VCCINT_MIN   = 0x25
    XADC_REG_VCCAUX_MIN   = 0x26
    XADC_REG_VCCBRAM_MIN  = 0x27
    XADC_REG_VCCPINT_MAX  = 0x28
    XADC_REG_VCCPAUX_MAX  = 0x29
    XADC_REG_VCCODDR_MAX  = 0x2a
    XADC_REG_VCCPINT_MIN  = 0x2c
    XADC_REG_VCCPAUX_MIN  = 0x2d
    XADC_REG_VCCODDR_MIN  = 0x2e
    XADC_REG_SUP_B_OFFSET = 0x30
    XADC_REG_ADC_B_OFFSET = 0x31
    XADC_REG_ADC_B_GAIN   = 0x32
    XADC_REG_FLAG         = 0x3f
    XADC_FLAG_JTGD         = (1 << 11)
    XADC_FLAG_JTGR         = (1 << 10)
    XADC_FLAG_REF          = (1 << 9)
    XADC_FLAG_ALM6         = (1 << 7)
    XADC_FLAG_ALM5         = (1 << 6)
    XADC_FLAG_ALM4         = (1 << 5)
    XADC_FLAG_ALM3         = (1 << 4)
    XADC_FLAG_OT           = (1 << 4)
    XADC_FLAG_ALM2         = (1 << 2)
    XADC_FLAG_ALM1         = (1 << 1)
    XADC_FLAG_ALM0         = (1 << 0)
    XADC_REG_CONFIG       = staticmethod(lambda x:0x40+x)
    XADC_CFG0_CHANNEL      = staticmethod(lambda x:x)
    XADC_CFG0_ACQ          = 0x0100
    XADC_CFG0_EVENT_DRIVEN = 0x0200
    XADC_CFG0_BIPOLAR      = 0x0400
    XADC_CFG0_MUX          = 0x0800
    XADC_CFG0_AVG          = staticmethod(lambda x:x<<12)
    XADC_CFG0_CAVG         = 0x8000
    XADC_CFG1_OT_DISABLE   = 0x0001
    XADC_CFG1_ALM0         = 0x0002
    XADC_CFG1_ALM1         = 0x0004
    XADC_CFG1_ALM2         = 0x0008
    XADC_CFG1_CAL0         = 0x0008
    XADC_CFG1_CAL1         = 0x0010
    XADC_CFG1_CAL2         = 0x0020
    XADC_CFG1_CAL3         = 0x0040
    XADC_CFG1_ALM3         = 0x0080
    XADC_CFG1_SEQ          = staticmethod(lambda x:x<<12)
    XADC_SEQ_DEFAULT        = 0
    XADC_SEQ_SINGLE_PASS    = 1
    XADC_SEQ_CONTINUOUS     = 2
    XADC_SEQ_SIGNLE_CHANNEL = 3
    XADC_SEQ_SIMULTANEOUS   = 8
    XADC_SEQ_INDEPENDENT    = 12
    XADC_CFG2_PD0          = 0x0010
    XADC_CFG2_PD2          = 0x0020
    XADC_CFG2_CD           = staticmethod(lambda x:x << 8)
    XADC_REG_TEST         = staticmethod(lambda x:0x43+x)
    XADC_REG_SEQUENCE     = staticmethod(lambda x:0x48+x)
    XADC_REG_ALARM        = staticmethod(lambda x:0x50+x)

    XADC_CHANNEL_TEMP         = 0
    XADC_CHANNEL_VCCINT       = 1
    XADC_CHANNEL_VCCAUX       = 2
    XADC_CHANNEL_V_PN         = 3
    XADC_CHANNEL_VREF_P       = 4
    XADC_CHANNEL_VREF_N       = 5
    XADC_CHANNEL_VCCBRAM      = 6
    XADC_CHANNEL_CALIB        = 8
    XADC_CHANNEL_VCCPINT      = 13
    XADC_CHANNEL_VCCPAUX      = 14
    XADC_CHANNEL_VCCODDR      = 15
    XADC_CHANNEL_VAUX_PN      = staticmethod(lambda x: x+16)

    def cmd_xadc_write(self, address, data):
        return [self.cmd_dr_shift(self.IR_XADC_DRP, 0x08000000 | (address << 16) | data, 32),
                self.cmd_run(10)]

    def cmd_xadc_read(self, address):
        return [self.cmd_dr_shift(self.IR_XADC_DRP, 0x04000000 | (address << 16), 32),
                self.cmd_run(10),
                self.cmd_dr_shift(self.IR_XADC_DRP, 0, 32),
                self.cmd_run(10)]

    def xadc_write(self, address, data):
        cmds = self.cmd_xadc_write(address, data)
        self.execute(cmds)

    def xadc_read(self, address):
        cmds = self.cmd_xadc_read(address)
        self.execute(cmds)
        return cmds[2].tdo

    def xadc_init_defaults(self):
        cmds = self.cmd_xadc_write(self.XADC_REG_CONFIG(1), self.XADC_CFG1_SEQ(self.XADC_SEQ_DEFAULT))
        self.execute(cmds)

    def xadc_value_read(self, channel):
        cmds = self.cmd_xadc_read(self.XADC_REG_VALUE(channel))
        self.execute(cmds)
        return min(max(0, int(cmds[-2].tdo) >> 4), 0xfff) / 0xfff

    def xadc_temperature_read(self):
        return self.xadc_value_read(self.XADC_CHANNEL_TEMP) * 503.975 - 273.15
