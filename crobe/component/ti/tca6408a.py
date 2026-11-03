from ...protocol import i2c
import enum

class Reg(enum.IntEnum):
    Input = 0x00
    Output = 0x01
    PolarityInversion = 0x02
    Configuration = 0x03

class GpioMode(enum.IntEnum):
    Output = 0x00
    Input = 0x01

class GpioState(enum.IntEnum):
    Low = 0x00
    High = 0x01
    
@i2c.Interface.db.register("tca6408a")
class Tca6408a(i2c.Slave):
    def __init__(self, port, saddr):
        super().__init__(port, "tca6408a", saddr)

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

    def get_output_config_regs(self):
        output_reg = self.reg_read(Reg.Output)
        config_reg = self.reg_read(Reg.Configuration)
        return (output_reg, config_reg)

    def get_gpio_values(self):
        input_reg = self.reg_read(Reg.Input)
        return [
            GpioState.High if input_reg & (1 << i) else GpioState.Low
            for i in range(8)
        ]

    def set_config(self, gpio_configs):
        '''
        Takes a list of gpio configs. These are tuples of:
        - (GpioMode, GpioState)
        '''
        output_reg = 0
        config_reg = 0
        for i, (mode, level) in enumerate(gpio_configs):
            if mode == GpioMode.Input:
                config_reg |= 1 << i
            elif level == GpioState.High:
                output_reg |= 1 << i

        self.reg_write(Reg.Output, output_reg)
        self.reg_write(Reg.Configuration, config_reg)
