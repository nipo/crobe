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
        Register.Config: 2,
        Register.AdcConfig: 2,
        Register.ShuntCalib: 2,
        Register.ShuntTempCoef: 2,
        Register.VShunt: 3,
        Register.VBus: 3,
        Register.Temperature: 2,
        Register.Current: 3,
        Register.Power: 3,
        Register.Energy: 5,
        Register.Charge: 5,
        Register.DiagAlert: 2,
        Register.ShuntOverVoltage: 2,
        Register.ShuntUnderVoltage: 2,
        Register.BusOverVoltage: 2,
        Register.BusUnderVoltage: 2,
        Register.TempLimit: 2,
        Register.PowerLimit: 2,
        Register.ManufId: 2,
        Register.DeviceId: 2,
    }
    
    def __init__(self, port):
        super().__init__(port, "ina229")

    def reg_read(self, reg):
        reg_size = self._register_size[Register(reg)]
        cmd = self.port.cmd_shift(bytes([(int(reg) << 2) | 1]), read_miso = False)
        data = self.port.cmd_shift(b"\x00" * reg_size, read_miso = True)

        self.port.execute([self.port.cmd_cs(True), cmd, data, self.port.cmd_cs(False)])

        return int.from_bytes(data.miso, "big")

    def reg_write(self, reg, value):
        reg_size = self._register_size[Register(reg)]
        blob = int(value).to_bytes(reg_size, "big")

        cmd = self.port.cmd_shift(bytes([int(reg) << 2]) + blob, read_miso = False)

        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])

    def start(self):
        manufid = self.reg_read(Register.ManufId)
        devid = self.reg_read(Register.DeviceId)

        self.logger.info("Device manufacturer code: %04x (%s), device ID: %04x",
                         manufid, manufid.to_bytes(2, "big"),
                         devid)
