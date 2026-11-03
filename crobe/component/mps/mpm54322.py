from ...protocol import i2c
import enum

class Reg(enum.IntEnum):
    LOCK         = 0x00
    BUCK1_CTRL1  = 0x01
    BUCK1_CTRL2  = 0x02
    BUCK1_CTRL3  = 0x03
    BUCK1_CTRL4  = 0x04
    BUCK1_CTRL7  = 0x05
    BUCK2_CTRL1  = 0x06
    BUCK2_CTRL2  = 0x07
    BUCK2_CTRL3  = 0x08
    BUCK2_CTRL4  = 0x09
    BUCK2_CTRL7  = 0x0A
    LDO_CTRL1    = 0x0B
    LDO_CTRL2    = 0x0C
    SYS_CTRL1    = 0x0D
    SYS_CTRL3    = 0x0E
    SYS_CTRL4    = 0x0F
    ADC_CTRL1    = 0x10
    TEMPERATURE  = 0x11
    VOUT1_ADC    = 0x12
    IOUT1_ADC    = 0x13
    VOUT2_ADC    = 0x14
    IOUT2_ADC    = 0x15
    LDO_ADC      = 0x16
    GPIO_ADC     = 0x17
    VIN_ADC      = 0x18
    FAULT_STATUS = 0x19
    STATUS1      = 0x1A
    MASK1        = 0x1B
    MASK2        = 0x1C
    CLEAR1       = 0x1D
    CLEAR2       = 0x1E
    AVP_CTRL1    = 0x1F
    AVP_CTRL2    = 0x20
    STATUS2      = 0x21
    
class SysCtrl1_BitMask(enum.IntEnum):
    PMIC_EN        = 0x80
    VOUT1_EN       = 0x40
    VOUT2_EN       = 0x20
    LDO_EN         = 0x10
    GPIO_CTRL_MASK = 0x03

class BuckCtrl1_BitMask(enum.IntEnum):
    GO_BIT         = 0x80  # D[7]: self-clearing, triggers voltage scaling
    SLEW_RATE_MASK = 0x03  # D[1:0]: 00=0.5mV/us, 01=1mV/us, 10=2mV/us, 11=4mV/us

class BuckCtrl2_BitMask(enum.IntEnum):
    PFM_PWM_MASK     = 0xC0  # D[7:6]: 10=COT, 11=FCCM
    FSW_MASK         = 0x30  # D[5:4]: 00=500kHz, 01=750kHz, 10=1MHz, 11=1.25MHz
    SETTING_LOW_MASK = 0x07  # D[2:0]: works with SETTING_HIGH for VOUT

class BuckCtrl4_BitMask(enum.IntEnum):
    DISCHRG_EN = 0x80  # D[7]: passive discharge enable
    OVP_EN     = 0x40  # D[6]: active OVP enable
    OC_TH_MASK = 0x1C  # D[4:2]: OC threshold 000=4A..111=7.5A

class BuckCtrl7_BitMask(enum.IntEnum):
    PG_VTH_HIGH_MASK = 0xC0  # D[7:6]: PG high threshold
    PG_VTH_LOW       = 0x20  # D[5]: 0=-7.5%, 1=-10%
    UV_VTH_MASK      = 0x0C  # D[3:2]: UV threshold
    OV_VTH_MASK      = 0x03  # D[1:0]: OV threshold

class LdoCtrl1_BitMask(enum.IntEnum):
    GO_BIT  = 0x80  # D[7]: self-clearing
    DISCHG  = 0x02  # D[1]: LDO discharge enable
    PG_VTH  = 0x01  # D[0]: 0=-10%, 1=-15%

class SysCtrl3_BitMask(enum.IntEnum):
    VIN_PG_VTH_MASK = 0xE0  # D[7:5]: VIN PG threshold
    MASK_PG         = 0x10  # D[4]: mask INT for PG

class SysCtrl4_BitMask(enum.IntEnum):
    OT_TH_MASK  = 0xE0  # D[7:5]: OT shutdown threshold
    OTW_TH_MASK = 0x1C  # D[4:2]: OT warning threshold

class AdcCtrl1_BitMask(enum.IntEnum):
    ADC_EN           = 0x80  # D[7]: enable ADC
    SAMPLE_FREQ_MASK = 0x03  # D[1:0]: 00=4kHz, 01=2kHz, 10=1kHz, 11=0.5kHz

class FaultStatus_BitMask(enum.IntEnum):
    VIN_PG      = 0x80
    VOUT1_FAULT = 0x40
    VOUT2_FAULT = 0x20
    LDO_FAULT   = 0x10
    OTW         = 0x02
    OT          = 0x01

class Status1_BitMask(enum.IntEnum):
    VIN_OV   = 0x80
    VIN_UV   = 0x40
    VOUT1_OV = 0x20
    VOUT2_OV = 0x10
    VOUT1_UV = 0x08
    VOUT2_UV = 0x04
    VOUT1_OC = 0x02
    VOUT2_OC = 0x01

@i2c.Interface.db.register("mpm54322")
class Mpm54322(i2c.Slave):

    TEMPERATURE_TABLE = [
        80,  #0  T<80
        85,  #1
        95,  #2
        105, #3
        115, #4
        125, #5
        135, #6
        140  #7  T>140
    ]

    def __init__(self, port, saddr):
        super().__init__(port, "mpm54322", saddr)

    def reg_read(self, reg):
        reg = int(reg)
        rdata = self.write_read(bytes([reg]), 1)
        value = rdata[0]
        self.logger.trace("Reg read 0x%02x: 0x%02x", reg, value)
        return value

    def reg_write(self, reg, value):
        reg = int(reg)
        value = int(value) & 0xff
        self.logger.trace("Reg write 0x%02x: 0x%02x", reg, value)
        self.write(bytes([reg, value]))

    def unlock_i2c_writes(self):
        self.reg_write(Reg.LOCK, 0x00)

    def lock_i2c_writes(self):
        # I2C writes are ineffective when LOCK_EN=1 
        self.reg_write(Reg.LOCK, 0x01)

    def write_sys_ctrl1(self, pmic_en, vout1_en, vout2_en, ldo_en, gpio_ctrl=0):
        value = 0
        if pmic_en:
            value |= SysCtrl1_BitMask.PMIC_EN
        if vout1_en:
            value |= SysCtrl1_BitMask.VOUT1_EN
        if vout2_en:
            value |= SysCtrl1_BitMask.VOUT2_EN
        if ldo_en:
            value |= SysCtrl1_BitMask.LDO_EN
        value |= int(gpio_ctrl) & SysCtrl1_BitMask.GPIO_CTRL_MASK
        self.reg_write(Reg.SYS_CTRL1, value)

    def read_vout1_adc(self):
        return self.reg_read(Reg.VOUT1_ADC) * 0.016 # 16mV per LSB

    def read_vout2_adc(self):
        return self.reg_read(Reg.VOUT2_ADC) * 0.016 # 16mV per LSB

    def read_iout1_adc(self):
        return self.reg_read(Reg.IOUT1_ADC) * 0.050 #50mA per LSB

    def read_iout2_adc(self):
        return self.reg_read(Reg.IOUT2_ADC) * 0.050 #50mA per LSB

    def read_vin_adc(self):
        return self.reg_read(Reg.VIN_ADC) * 0.064 #64mV per LSB

    def read_ldo_adc(self):
        return self.reg_read(Reg.LDO_ADC) * 0.016 #16mV per LSB

    def read_gpio_adc(self):
        return self.reg_read(Reg.GPIO_ADC) * 0.008 #8mV per LSB

    def read_temperature(self):
        return self.TEMPERATURE_TABLE[(self.reg_read(Reg.TEMPERATURE) >> 5) & 0x7]

    def read_fault_status(self):
        return self.reg_read(Reg.FAULT_STATUS)

    def read_status1(self):
        return self.reg_read(Reg.STATUS1)

    def power_on(self, vout1_en=True, vout2_en=True, ldo_en=False, gpio_ctrl=0):
        self.unlock_i2c_writes()
        self.write_sys_ctrl1(True, vout1_en, vout2_en, ldo_en, gpio_ctrl)
        self.lock_i2c_writes()

    def power_off(self):
        self.unlock_i2c_writes()
        self.write_sys_ctrl1(False, False, False, False)
        self.lock_i2c_writes()

    def enable_adc(self, sample_freq=0):
        self.unlock_i2c_writes()
        value = AdcCtrl1_BitMask.ADC_EN | (int(sample_freq) & AdcCtrl1_BitMask.SAMPLE_FREQ_MASK)
        self.reg_write(Reg.ADC_CTRL1, value)
        self.lock_i2c_writes()

    def read_telemetry(self):
        return {
            'vout1_mv': self.read_vout1_adc(),
            'vout2_mv': self.read_vout2_adc(),
            'iout1_ma': self.read_iout1_adc(),
            'iout2_ma': self.read_iout2_adc(),
            'vin_mv':   self.read_vin_adc(),
            'ldo_mv':   self.read_ldo_adc(),
            'temp':     self.read_temperature(),
        }

    def check_faults(self):
        fault = self.read_fault_status()
        status = self.read_status1()
        faults = []
        for f in FaultStatus_BitMask:
            if fault & f:
                faults.append(f.name)
        for s in Status1_BitMask:
            if status & s:
                faults.append(s.name)
        return faults

    def clear_faults(self):
        self.unlock_i2c_writes()
        self.reg_write(Reg.CLEAR1, 0xFF)
        self.reg_write(Reg.CLEAR2, 0xFF)
        self.lock_i2c_writes()
