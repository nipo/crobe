from ...model import PortComponent
from ...protocol import spi
import enum

class Register(enum.IntEnum):
    Config = 0
    AdcConfig = 1
    ShuntCalib = 2
    ShuntTempCoef = 3
    VShunt = 4
    VBus = 5
    Temperature = 6
    Current = 7
    Power = 8
    Energy = 9
    Charge = 0xa
    DiagAlert = 0xb
    ShuntOverVoltage = 0xc
    ShuntUnderVoltage = 0xd
    BusOverVoltage = 0xe
    BusUnderVoltage = 0xf
    TempLimit = 0x10
    PowerLimit = 0x11
    ManufId = 0x3e
    DeviceId = 0x3f

@spi.Target.db.register("ina229")
class Ina229(PortComponent):
    _register_size = {
        Register.Config: (2, False),
        Register.AdcConfig: (2, False),
        Register.ShuntCalib: (2, False),
        Register.ShuntTempCoef: (2, False),
        Register.VShunt: (3, False),
        Register.VBus: (3, False),
        Register.Temperature: (2, False),
        Register.Current: (3, False),
        Register.Power: (3, False),
        Register.Energy: (5, False),
        Register.Charge: (5, False),
        Register.DiagAlert: (2, False),
        Register.ShuntOverVoltage: (2, False),
        Register.ShuntUnderVoltage: (2, False),
        Register.BusOverVoltage: (2, False),
        Register.BusUnderVoltage: (2, False),
        Register.TempLimit: (2, False),
        Register.PowerLimit: (2, False),
        Register.ManufId: (2, False),
        Register.DeviceId: (2, False),
    }
    
    def __init__(self, port):
        super().__init__(port, "ina229")

    def reg_read(self, reg):
        reg_size, signed = self._register_size[Register(reg)]
        cmd = self.port.cmd_shift(bytes([(int(reg) << 2) | 1]), read_miso = False)
        data = self.port.cmd_shift(b"\x00" * reg_size, read_miso = True)

        self.port.execute([self.port.cmd_cs(True), cmd, data, self.port.cmd_cs(False)])

        return int.from_bytes(data.miso, "big", signed = signed)

    def reg_write(self, reg, value):
        reg_size, signed = self._register_size[Register(reg)]
        blob = int(value).to_bytes(reg_size, "big", signed = signed)

        cmd = self.port.cmd_shift(bytes([int(reg) << 2]) + blob, read_miso = False)

        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])

    def temperature_get(self):
        v = self.reg_read(Register.Temperature)
        return v/128

    def start(self):
        manufid = self.reg_read(Register.ManufId)
        devid = self.reg_read(Register.DeviceId)

        self.logger.info("Device manufacturer code: %04x (%s), device ID: %04x",
                         manufid, manufid.to_bytes(2, "big"),
                         devid)
