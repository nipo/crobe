from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
import enum
import decimal

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

class GpioCfg(enum.IntEnum):
    SW_CTRL_GPIO   = 0
    ERROR_RECOVERY = 1
    DEBUG          = 2
    SINK_POWER     = 3

class Bank0(Bitfield):
    all = Field(0, 64)
    VendorId = Field(0, 16)
    ProductId = Field(16, 16)
    BcdDevice = Field(32, 16)
    PortRoleCtrl = Field(48, 8)
    DevicePowerRoleCtrl = Field(56, 8)

class Bank1(Bitfield):
    all = Field(0, 64)
    GpioCfg = EnumField(4, 2, GpioCfg)
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
    SnkPdoNumb = Field(17, 2)
    SnkUnconsPower = BooleanField(19)
    LutSnkPdo1 = Field(20, 4)
    SnkHl1 = Field(28, 4, doc = "PDO1 OVLO, percent - 5")
    LutSnkPdo2 = Field(32, 4)
    SnkLl2 = Field(36, 4, doc = "PDO2 UVLO, percent - 5")
    SnkHl2 = Field(40, 4, doc = "PDO2 OVLO, percent - 5")
    LutSnkPdo3 = Field(44, 4)
    SnkLl3 = Field(48, 4, doc = "PDO3 UVLO, percent - 5")
    SnkHl3 = Field(52, 4, doc = "PDO3 OVLO, percent - 5")

class Bank4(Bitfield):
    all = Field(0, 64)
    SnkPdoFlex1V = Field(6, 10, doc = "PDO2 voltage, 50mV unit")
    SnkPdoFlex2V = Field(16, 10, doc = "PDO3 voltage, 50mV unit")
    SnkPdoFlexI = Field(26, 10, doc = "Flex current, 10mA unit")
    PowerOkCfg = Field(37, 2)
    PowerOnlyAbove5V = BooleanField(51)
    ReqSrcCurrent = BooleanField(52)
    AlertStatus1Mask = Field(56, 8)

class StUsb4500Nvm:
    """
    Customization NVM contents of STUSB4500, as 5 sectors of 8 bytes.

    Only documented fields are exposed, other bits are kept as-is from
    the sectors the object is built from.  Voltages are in mV,
    currents in mA.
    """

    BANKS = (Bank0, Bank1, Bank2, Bank3, Bank4)

    DEFAULT = (
        bytes.fromhex("0000b0aa00450000"),
        bytes.fromhex("10409c1cff013cdf"),
        bytes.fromhex("02400f003200fcf1"),
        bytes.fromhex("001956aff5355f00"),
        bytes.fromhex("004b9021430040fb"),
        )

    PDO_COUNT = 3
    PDO1_VOLTAGE = 5000
    VOLTAGE_RANGE = (5000, 20000)
    VOLTAGE_STEP = 50
    FLEX_CURRENT_MAX = 5000
    FLEX_CURRENT_STEP = 10
    LIMIT_RANGE = (5, 20)
    POWER_OK_CFGS = (0, 2, 3)

    CONFIG_KEYS = {"base", "pdo", "pdo_count", "flex_current",
                   "usb_comm_capable", "snk_uncons_power", "gpio_cfg",
                   "power_ok_cfg", "power_only_above_5v", "req_src_current"}
    PDO_KEYS = {"voltage", "current", "uvlo", "ovlo"}

    def __init__(self, sectors = DEFAULT):
        if len(sectors) != len(self.BANKS):
            raise ValueError(f"Expected {len(self.BANKS)} sectors, got {len(sectors)}")
        self.banks = []
        for bank, data in zip(self.BANKS, sectors):
            if len(data) != 8:
                raise ValueError(f"Sector must be 8 bytes, got {len(data)}")
            self.banks.append(bank(int.from_bytes(data, "little")))

    def sectors(self):
        return [int(b).to_bytes(8, "little") for b in self.banks]

    @staticmethod
    def current_decode(code):
        if code == 0:
            return None
        if code <= 10:
            return 250 * code + 250
        return 500 * code - 2500

    @classmethod
    def current_encode(cls, ma):
        if ma is None:
            return 0
        for code in range(1, 16):
            if cls.current_decode(code) == ma:
                return code
        raise ValueError(f"Current {ma}mA is not representable, use one of "
                         + ", ".join(f"{cls.current_decode(c)}mA" for c in range(1, 16))
                         + " or flex")

    @staticmethod
    def check_range(name, value, low, high, step = 1):
        if not low <= value <= high or value % step:
            raise ValueError(f"{name} {value} is not in [{low}, {high}] by steps of {step}")

    @property
    def pdo_count(self):
        return self.banks[3].SnkPdoNumb

    @pdo_count.setter
    def pdo_count(self, value):
        self.check_range("PDO count", value, 1, self.PDO_COUNT)
        self.banks[3].SnkPdoNumb = value

    def pdo_check(self, n):
        if not 1 <= n <= self.PDO_COUNT:
            raise ValueError(f"No PDO{n}")

    def pdo_voltage(self, n):
        self.pdo_check(n)
        if n == 1:
            return self.PDO1_VOLTAGE
        if n == 2:
            return self.banks[4].SnkPdoFlex1V * self.VOLTAGE_STEP
        return self.banks[4].SnkPdoFlex2V * self.VOLTAGE_STEP

    def pdo_voltage_set(self, n, mv):
        self.pdo_check(n)
        if n == 1:
            if mv != self.PDO1_VOLTAGE:
                raise ValueError(f"PDO1 voltage is fixed to {self.PDO1_VOLTAGE}mV")
            return
        self.check_range(f"PDO{n} voltage", mv, *self.VOLTAGE_RANGE, self.VOLTAGE_STEP)
        if n == 2:
            self.banks[4].SnkPdoFlex1V = mv // self.VOLTAGE_STEP
        else:
            self.banks[4].SnkPdoFlex2V = mv // self.VOLTAGE_STEP

    def pdo_lut_field(self, n):
        self.pdo_check(n)
        return f"LutSnkPdo{n}"

    def pdo_current(self, n):
        """Returns PDO current in mA, or None if flex current is used"""
        return self.current_decode(getattr(self.banks[3], self.pdo_lut_field(n)))

    def pdo_current_set(self, n, ma):
        setattr(self.banks[3], self.pdo_lut_field(n), self.current_encode(ma))

    def pdo_limit_field(self, n, kind):
        self.pdo_check(n)
        if kind == "uvlo":
            if n == 1:
                raise ValueError("PDO1 has no UVLO setting")
            return f"SnkLl{n}"
        if kind == "ovlo":
            return f"SnkHl{n}"
        raise ValueError(kind)

    def pdo_limit(self, n, kind):
        """Returns PDO UVLO or OVLO threshold, in percent"""
        return getattr(self.banks[3], self.pdo_limit_field(n, kind)) + self.LIMIT_RANGE[0]

    def pdo_limit_set(self, n, kind, percent):
        self.check_range(f"PDO{n} {kind}", percent, *self.LIMIT_RANGE)
        setattr(self.banks[3], self.pdo_limit_field(n, kind), percent - self.LIMIT_RANGE[0])

    @property
    def flex_current(self):
        return self.banks[4].SnkPdoFlexI * self.FLEX_CURRENT_STEP

    @flex_current.setter
    def flex_current(self, ma):
        self.check_range("Flex current", ma, 0, self.FLEX_CURRENT_MAX, self.FLEX_CURRENT_STEP)
        self.banks[4].SnkPdoFlexI = ma // self.FLEX_CURRENT_STEP

    @property
    def usb_comm_capable(self):
        return self.banks[3].UsbCommCapable

    @usb_comm_capable.setter
    def usb_comm_capable(self, value):
        self.banks[3].UsbCommCapable = value

    @property
    def snk_uncons_power(self):
        return self.banks[3].SnkUnconsPower

    @snk_uncons_power.setter
    def snk_uncons_power(self, value):
        self.banks[3].SnkUnconsPower = value

    @property
    def gpio_cfg(self):
        return GpioCfg(self.banks[1].GpioCfg)

    @gpio_cfg.setter
    def gpio_cfg(self, value):
        self.banks[1].GpioCfg = GpioCfg(value)

    @property
    def power_ok_cfg(self):
        return self.banks[4].PowerOkCfg

    @power_ok_cfg.setter
    def power_ok_cfg(self, value):
        if value not in self.POWER_OK_CFGS:
            raise ValueError(f"Power OK config must be one of {self.POWER_OK_CFGS}")
        self.banks[4].PowerOkCfg = value

    @property
    def power_only_above_5v(self):
        return self.banks[4].PowerOnlyAbove5V

    @power_only_above_5v.setter
    def power_only_above_5v(self, value):
        self.banks[4].PowerOnlyAbove5V = value

    @property
    def req_src_current(self):
        return self.banks[4].ReqSrcCurrent

    @req_src_current.setter
    def req_src_current(self, value):
        self.banks[4].ReqSrcCurrent = value

    @staticmethod
    def quantity_parse(value, unit):
        """
        Parses a quantity like "12V", "500mA", or a bare number in
        base unit, returns an integer in milli-units.
        """
        if isinstance(value, bool):
            raise ValueError(f"Invalid quantity {value!r}")
        if isinstance(value, (int, float)):
            number = decimal.Decimal(str(value))
        elif isinstance(value, str):
            v = value.strip()
            scale = 1
            if v.endswith("m" + unit):
                v = v[:-len(unit) - 1]
                scale = decimal.Decimal("0.001")
            elif v.endswith(unit):
                v = v[:-len(unit)]
            try:
                number = decimal.Decimal(v.strip()) * scale
            except decimal.InvalidOperation:
                raise ValueError(f"Invalid quantity {value!r}")
        else:
            raise ValueError(f"Invalid quantity {value!r}")
        milli = number * 1000
        if milli != milli.to_integral_value():
            raise ValueError(f"Quantity {value!r} is finer than 1m{unit}")
        return int(milli)

    @staticmethod
    def quantity_format(milli, unit):
        return f"{(decimal.Decimal(milli) / 1000).normalize():f}{unit}"

    @staticmethod
    def bool_parse(name, value):
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean, got {value!r}")
        return value

    @classmethod
    def from_config(cls, config, base_sectors):
        """
        Builds NVM contents from base sectors updated by config
        dictionary.  Keys absent from config keep their base value.
        """
        unknown = set(config) - cls.CONFIG_KEYS
        if unknown:
            raise ValueError(f"Unknown keys: {', '.join(sorted(unknown))}")

        self = cls(base_sectors)

        pdos = config.get("pdo", [])
        if len(pdos) > cls.PDO_COUNT:
            raise ValueError(f"At most {cls.PDO_COUNT} PDOs")
        for n, pdo in enumerate(pdos, 1):
            unknown = set(pdo) - cls.PDO_KEYS
            if unknown:
                raise ValueError(f"PDO{n}: unknown keys: {', '.join(sorted(unknown))}")
            if "voltage" in pdo:
                self.pdo_voltage_set(n, cls.quantity_parse(pdo["voltage"], "V"))
            if "current" in pdo:
                current = pdo["current"]
                self.pdo_current_set(n, None if current == "flex" else cls.quantity_parse(current, "A"))
            for kind in ("uvlo", "ovlo"):
                if kind in pdo:
                    self.pdo_limit_set(n, kind, pdo[kind])

        if "pdo_count" in config:
            self.pdo_count = config["pdo_count"]
        if "flex_current" in config:
            self.flex_current = cls.quantity_parse(config["flex_current"], "A")
        for name in ("usb_comm_capable", "snk_uncons_power",
                     "power_only_above_5v", "req_src_current"):
            if name in config:
                setattr(self, name, cls.bool_parse(name, config[name]))
        if "gpio_cfg" in config:
            try:
                self.gpio_cfg = GpioCfg[config["gpio_cfg"].upper()]
            except (KeyError, AttributeError):
                raise ValueError(f"gpio_cfg must be one of "
                                 + ", ".join(g.name.lower() for g in GpioCfg))
        if "power_ok_cfg" in config:
            self.power_ok_cfg = config["power_ok_cfg"]

        return self

    def to_config(self):
        pdos = []
        for n in range(1, self.PDO_COUNT + 1):
            pdo = {}
            if n != 1:
                pdo["voltage"] = self.quantity_format(self.pdo_voltage(n), "V")
            current = self.pdo_current(n)
            pdo["current"] = "flex" if current is None else self.quantity_format(current, "A")
            if n != 1:
                pdo["uvlo"] = self.pdo_limit(n, "uvlo")
            pdo["ovlo"] = self.pdo_limit(n, "ovlo")
            pdos.append(pdo)

        return {
            "pdo": pdos,
            "pdo_count": self.pdo_count,
            "flex_current": self.quantity_format(self.flex_current, "A"),
            "usb_comm_capable": self.usb_comm_capable,
            "snk_uncons_power": self.snk_uncons_power,
            "gpio_cfg": self.gpio_cfg.name.lower(),
            "power_ok_cfg": self.power_ok_cfg,
            "power_only_above_5v": self.power_only_above_5v,
            "req_src_current": self.req_src_current,
        }

    def pretty(self, printer):
        for n in range(1, self.PDO_COUNT + 1):
            current = self.pdo_current(n)
            if current is None:
                current = self.flex_current
                flex = " (flex)"
            else:
                flex = ""
            uvlo = f"-{self.pdo_limit(n, 'uvlo')}%/" if n != 1 else ""
            printer(f"PDO{n}: {self.quantity_format(self.pdo_voltage(n), 'V')}"
                    f" {self.quantity_format(current, 'A')}{flex}"
                    f", window {uvlo}+{self.pdo_limit(n, 'ovlo')}%"
                    + ("" if n <= self.pdo_count else ", unused"))
        for k, v in self.to_config().items():
            if k != "pdo":
                printer(f"{k}: {v}")
        for i, s in enumerate(self.sectors()):
            printer(f"Sector {i}: {s.hex()}")

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

    def customization_get(self):
        self.cust_read_mode_enter()
        sectors = [self.cust_sector_read(i) for i in range(len(StUsb4500Nvm.BANKS))]
        self.cust_test_mode_exit()
        return sectors

    def customization_set(self, sector_data):
        self.cust_write_mode_enter()
        for i, data in enumerate(sector_data):
            self.cust_sector_write(i, data)
        self.cust_test_mode_exit()
