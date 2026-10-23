from ...protocol import i2c
from ...bitfield import *
import enum
import decimal
import time

class Max31760Register(enum.IntEnum):
    CR1  = 0x00
    CR2  = 0x01
    CR3  = 0x02
    FFDC = 0x03
    MASK = 0x04
    IFR  = 0x05
    RHSH = 0x06
    LOTSH = 0x08
    ROTSH = 0x0a
    LHSH = 0x0c
    TCTH = 0x0e
    USER = 0x10
    LUT  = 0x20
    PWMR = 0x50
    PWMV = 0x51
    TC1H = 0x52
    TC2H = 0x54
    RTH  = 0x56
    LTH  = 0x58
    SR   = 0x5a
    EEX  = 0x5b

class Cr1(Bitfield):
    all = Field(0, 8)
    Tis = BooleanField(0, doc = "Use remote temperature as LUT index")
    Mti = BooleanField(1, doc = "Use max of local and remote temperature as LUT index")
    Pps = Field(2, 1, doc = "PWM polarity")
    Drv = Field(3, 2, doc = "PWM frequency")
    Hyst = Field(5, 1, doc = "LUT hysteresis")
    Por = BooleanField(6, doc = "Soft POR, self-clearing")
    AltMsk = BooleanField(7, doc = "Mask temperature alerts")

class Cr2(Bitfield):
    all = Field(0, 8)
    Dfc = BooleanField(0, doc = "Direct fan control")
    Fsst = Field(1, 1, doc = "Fan sense signal type")
    Rdps = Field(2, 1, doc = "RD signal polarity")
    FsEnable = BooleanField(3, doc = "FF/FS low forces 100% duty")
    FfMode = Field(4, 1, doc = "FF/FS output mode")
    Spen = BooleanField(5, doc = "Spin-up enable")
    Alerts = Field(6, 1, doc = "ALERT output mode")
    Stby = BooleanField(7, doc = "Standby")

class Cr3(Bitfield):
    all = Field(0, 8)
    Tach1E = BooleanField(0)
    Tach2E = BooleanField(1)
    Psen = BooleanField(2, doc = "Pulse stretch, 33Hz PWM only")
    TachFull = BooleanField(3, doc = "Detect fan failure at 100% duty only")
    Ramp = Field(4, 2, doc = "Duty cycle ramp rate")
    Ff0 = BooleanField(6, doc = "Detect fan failure at 0% duty")
    ClrFail = BooleanField(7, doc = "Clear fan failure, self-clearing")

class Mask(Bitfield):
    all = Field(0, 8)
    Tach1Am = BooleanField(0)
    Tach2Am = BooleanField(1)
    Rotam = BooleanField(2)
    Rham = BooleanField(3)
    Lotam = BooleanField(4)
    Lham = BooleanField(5)

class Status(Bitfield):
    all = Field(0, 8)
    Tach1Ff = BooleanField(0)
    Tach2Ff = BooleanField(1)
    Rota = BooleanField(2)
    Rha = BooleanField(3)
    Lota = BooleanField(4)
    Lha = BooleanField(5)
    Rdfa = BooleanField(6, doc = "Remote diode fault")
    Pc = BooleanField(7, doc = "Program corrupt")

class Max31760Eeprom:
    """
    Nonvolatile configuration of MAX31760, as the 80-byte image of
    registers 00h-4Fh.

    Temperatures are in °C, duty cycles in percent, rounded to the
    nearest 1/256 step, 100% being FFh.  Undocumented bytes 18h-1Fh
    are kept as-is from the image the object is built from.
    """

    SIZE = 0x50

    # Factory defaults, undocumented bytes 18h-1Fh are assumed zero
    DEFAULT = bytes.fromhex(
        "011003ffc018550055006e004600fffe"
        + "00" * 16
        + "ff" * 48)

    IDEALITY = tuple(decimal.Decimal(x) for x in (
        "0.9844", "0.9853", "0.9863", "0.9873", "0.9882", "0.9892", "0.9902", "0.9911",
        "0.9921", "0.9931", "0.9941", "0.9950", "0.9960", "0.9970", "0.9980", "0.9990",
        "1.0000", "1.0010", "1.0020", "1.0030", "1.0040", "1.0050", "1.0060", "1.0070",
        "1.0080", "1.0090", "1.0100", "1.0110", "1.0120", "1.0130", "1.0141", "1.0151",
        "1.0161", "1.0171", "1.0182", "1.0192", "1.0202", "1.0213", "1.0223", "1.0233",
        "1.0244", "1.0254", "1.0265", "1.0275", "1.0286", "1.0296", "1.0307", "1.0317",
        "1.0328", "1.0338", "1.0349", "1.0360", "1.0370", "1.0381", "1.0392", "1.0402",
        "1.0413", "1.0424", "1.0435", "1.0445", "1.0456", "1.0467", "1.0478", "1.0489",
        ))

    LUT_SIZE = 48
    LUT_LOW = 16
    LUT_STEP = 2

    TEMPERATURE_STEP = decimal.Decimal("0.125")
    TEMPERATURE_RANGE = (decimal.Decimal(-128), decimal.Decimal("127.875"))

    BOOLEANS = {
        "alert_masked": ("cr1", "AltMsk"),
        "standby": ("cr2", "Stby"),
        "spin_up": ("cr2", "Spen"),
        "full_speed_input": ("cr2", "FsEnable"),
        "direct_fan_control": ("cr2", "Dfc"),
        "pulse_stretch": ("cr3", "Psen"),
        "fan_fail_at_zero_duty": ("cr3", "Ff0"),
        "fan_fail_only_full_duty": ("cr3", "TachFull"),
        "tach1": ("cr3", "Tach1E"),
        "tach2": ("cr3", "Tach2E"),
        }

    CHOICES = {
        "hysteresis": ("cr1", "Hyst", (2, 4)),
        "pwm_frequency": ("cr1", "Drv", (33, 150, 1500, 25000)),
        "pwm_polarity": ("cr1", "Pps", ("positive", "negative")),
        "ramp_rate": ("cr3", "Ramp", (3.125, 6.25, 12.5, "immediate")),
        "alert_mode": ("cr2", "Alerts", ("interrupt", "comparator")),
        "fan_fail_mode": ("cr2", "FfMode", ("interrupt", "comparator")),
        "fan_sense": ("cr2", "Fsst", ("tach", "rd")),
        "rd_polarity": ("cr2", "Rdps", ("low", "high")),
        }

    TEMPERATURE_SOURCES = ("local", "remote", "max")

    MASKS = {
        "local_high": "Lham",
        "local_overtemp": "Lotam",
        "remote_high": "Rham",
        "remote_overtemp": "Rotam",
        "tach1": "Tach1Am",
        "tach2": "Tach2Am",
        }

    THRESHOLDS = {
        "remote_high": Max31760Register.RHSH,
        "local_overtemp": Max31760Register.LOTSH,
        "remote_overtemp": Max31760Register.ROTSH,
        "local_high": Max31760Register.LHSH,
        }

    CONFIG_KEYS = {"base", "temperature_source", "fan_fail_duty",
                   "tach_threshold", "ideality", "mask", "threshold",
                   "user", "lut"} | set(BOOLEANS) | set(CHOICES)

    def __init__(self, image = DEFAULT):
        if len(image) != self.SIZE:
            raise ValueError(f"Image must be {self.SIZE} bytes, got {len(image)}")
        self.cr1 = Cr1(image[Max31760Register.CR1])
        self.cr2 = Cr2(image[Max31760Register.CR2])
        self.cr3 = Cr3(image[Max31760Register.CR3])
        self.mask = Mask(image[Max31760Register.MASK])
        self.ffdc = image[Max31760Register.FFDC]
        self.ifr = image[Max31760Register.IFR]
        self.thresholds = {
            name: int.from_bytes(image[addr:addr+2], "big", signed = True)
            for name, addr in self.THRESHOLDS.items()
            }
        self.tct = int.from_bytes(image[Max31760Register.TCTH:Max31760Register.TCTH+2], "big")
        self.user = bytes(image[Max31760Register.USER:Max31760Register.USER+8])
        self.undocumented = bytes(image[0x18:Max31760Register.LUT])
        self.lut = list(image[Max31760Register.LUT:self.SIZE])

        if self.cr1.Por or self.cr3.ClrFail:
            raise ValueError("Self-clearing bits are set in image")
        if self.ifr >= len(self.IDEALITY):
            raise ValueError(f"Invalid ideality factor code {self.ifr:#04x}")

    def image(self):
        image = bytearray(self.SIZE)
        image[Max31760Register.CR1] = int(self.cr1)
        image[Max31760Register.CR2] = int(self.cr2)
        image[Max31760Register.CR3] = int(self.cr3)
        image[Max31760Register.FFDC] = self.ffdc
        image[Max31760Register.MASK] = int(self.mask)
        image[Max31760Register.IFR] = self.ifr
        for name, addr in self.THRESHOLDS.items():
            image[addr:addr+2] = self.thresholds[name].to_bytes(2, "big", signed = True)
        image[Max31760Register.TCTH:Max31760Register.TCTH+2] = self.tct.to_bytes(2, "big")
        image[Max31760Register.USER:Max31760Register.USER+8] = self.user
        image[0x18:Max31760Register.LUT] = self.undocumented
        image[Max31760Register.LUT:self.SIZE] = bytes(self.lut)
        return bytes(image)

    @property
    def temperature_source(self):
        if self.cr1.Mti:
            return "max"
        return "remote" if self.cr1.Tis else "local"

    @temperature_source.setter
    def temperature_source(self, value):
        if value not in self.TEMPERATURE_SOURCES:
            raise ValueError(f"temperature_source must be one of {', '.join(self.TEMPERATURE_SOURCES)}")
        if value == "max":
            self.cr1.Mti = True
        else:
            self.cr1.Mti = False
            self.cr1.Tis = value == "remote"

    def choice_get(self, name):
        register, field, values = self.CHOICES[name]
        return values[getattr(getattr(self, register), field)]

    def choice_set(self, name, value):
        register, field, values = self.CHOICES[name]
        if isinstance(value, bool) or value not in values:
            raise ValueError(f"{name} must be one of {', '.join(str(v) for v in values)}")
        setattr(getattr(self, register), field, values.index(value))

    def boolean_get(self, name):
        register, field = self.BOOLEANS[name]
        return getattr(getattr(self, register), field)

    def boolean_set(self, name, value):
        register, field = self.BOOLEANS[name]
        setattr(getattr(self, register), field, self.bool_parse(name, value))

    @property
    def ideality(self):
        return self.IDEALITY[self.ifr]

    @ideality.setter
    def ideality(self, value):
        try:
            self.ifr = self.IDEALITY.index(self.decimal_parse("ideality", value))
        except ValueError:
            raise ValueError(f"Ideality {value!r} is not in datasheet table, use one of "
                             + ", ".join(str(x) for x in self.IDEALITY))

    @property
    def tach_threshold(self):
        return self.tct

    @tach_threshold.setter
    def tach_threshold(self, value):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xffff:
            raise ValueError(f"tach_threshold {value!r} must be an integer in [0, 65535]")
        self.tct = value

    def threshold(self, name):
        return decimal.Decimal(self.thresholds[name]) / 256

    def threshold_set(self, name, value):
        t = self.decimal_parse(f"{name} threshold", value)
        low, high = self.TEMPERATURE_RANGE
        if not low <= t <= high or t % self.TEMPERATURE_STEP:
            raise ValueError(f"{name} threshold {value!r} is not in [{low}, {high}]"
                             f" by steps of {self.TEMPERATURE_STEP}")
        self.thresholds[name] = int(t * 256)

    def mask_set(self, name, value):
        setattr(self.mask, self.MASKS[name], self.bool_parse(f"mask {name}", value))

    @classmethod
    def lut_temperature(cls, index):
        """
        Lower bound of LUT entry window.  First entry also covers
        everything below.
        """
        return cls.LUT_LOW + cls.LUT_STEP * index

    def lut_breakpoints(self):
        """
        Returns LUT as a dictionary of temperature to duty code, with
        an entry for each window where duty changes.
        """
        r = {}
        for i, code in enumerate(self.lut):
            if i == 0 or code != self.lut[i - 1]:
                r[self.lut_temperature(i)] = code
        return r

    def lut_breakpoints_set(self, breakpoints):
        if not isinstance(breakpoints, dict):
            raise ValueError("lut must be a mapping of temperature to duty")
        temperatures = {self.lut_temperature(i): i for i in range(self.LUT_SIZE)}
        indices = {}
        for t, duty in breakpoints.items():
            if isinstance(t, bool) or t not in temperatures:
                raise ValueError(f"LUT temperature {t!r} must be one of "
                                 f"{self.lut_temperature(0)}, {self.lut_temperature(1)}, ..., "
                                 f"{self.lut_temperature(self.LUT_SIZE - 1)}")
            indices[temperatures[t]] = self.duty_parse(duty)
        if 0 not in indices:
            raise ValueError(f"LUT must have an entry for {self.lut_temperature(0)}")
        for i in range(self.LUT_SIZE):
            if i in indices:
                code = indices[i]
            self.lut[i] = code

    @staticmethod
    def decimal_parse(name, value):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"{name} {value!r} is not a number")
        try:
            return decimal.Decimal(str(value).strip())
        except decimal.InvalidOperation:
            raise ValueError(f"{name} {value!r} is not a number")

    @staticmethod
    def decimal_format(value):
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    @classmethod
    def duty_parse(cls, value):
        """
        Parses a duty cycle like "40%" or a bare number in percent,
        returns the nearest duty code.
        """
        if isinstance(value, str) and value.strip().endswith("%"):
            value = value.strip()[:-1]
        percent = cls.decimal_parse("Duty", value)
        if not 0 <= percent <= 100:
            raise ValueError(f"Duty {value!r} is not in [0%, 100%]")
        code = int((percent * 256 / 100).to_integral_value(decimal.ROUND_HALF_UP))
        return min(code, 0xff)

    @staticmethod
    def duty_format(code):
        if code == 0xff:
            return "100%"
        percent = (decimal.Decimal(code * 100) / 256).quantize(decimal.Decimal("0.1"), decimal.ROUND_HALF_UP)
        return f"{percent.normalize():f}%"

    @staticmethod
    def bool_parse(name, value):
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean, got {value!r}")
        return value

    @classmethod
    def from_config(cls, config, base_image):
        """
        Builds EEPROM contents from base image updated by config
        dictionary.  Keys absent from config keep their base value.
        """
        unknown = set(config) - cls.CONFIG_KEYS
        if unknown:
            raise ValueError(f"Unknown keys: {', '.join(sorted(unknown))}")

        self = cls(base_image)

        for name in cls.CHOICES:
            if name in config:
                self.choice_set(name, config[name])
        for name in cls.BOOLEANS:
            if name in config:
                self.boolean_set(name, config[name])
        if "temperature_source" in config:
            self.temperature_source = config["temperature_source"]
        if "fan_fail_duty" in config:
            self.ffdc = cls.duty_parse(config["fan_fail_duty"])
        if "tach_threshold" in config:
            self.tach_threshold = config["tach_threshold"]
        if "ideality" in config:
            self.ideality = config["ideality"]

        for key, names, setter in (("mask", cls.MASKS, self.mask_set),
                                   ("threshold", cls.THRESHOLDS, self.threshold_set)):
            sub = config.get(key, {})
            if not isinstance(sub, dict):
                raise ValueError(f"{key} must be a mapping")
            unknown = set(sub) - set(names)
            if unknown:
                raise ValueError(f"{key}: unknown keys: {', '.join(sorted(unknown))}")
            for name, value in sub.items():
                setter(name, value)

        if "user" in config:
            user = config["user"]
            try:
                user = bytes.fromhex(user)
            except (TypeError, ValueError):
                raise ValueError(f"user must be a hex string, got {user!r}")
            if len(user) != len(self.user):
                raise ValueError(f"user must be {len(self.user)} bytes, got {len(user)}")
            self.user = user

        if "lut" in config:
            self.lut_breakpoints_set(config["lut"])

        return self

    def to_config(self):
        return {
            "temperature_source": self.temperature_source,
            **{name: self.choice_get(name) for name in self.CHOICES},
            **{name: self.boolean_get(name) for name in self.BOOLEANS},
            "fan_fail_duty": self.duty_format(self.ffdc),
            "tach_threshold": self.tach_threshold,
            "ideality": float(self.ideality),
            "mask": {name: getattr(self.mask, field) for name, field in self.MASKS.items()},
            "threshold": {name: self.decimal_format(self.threshold(name)) for name in self.THRESHOLDS},
            "user": self.user.hex(),
            "lut": {t: self.duty_format(code) for t, code in self.lut_breakpoints().items()},
        }

    def pretty(self, printer):
        for k, v in self.to_config().items():
            if k == "lut":
                continue
            if isinstance(v, dict):
                v = ", ".join(f"{n}: {x}" for n, x in v.items())
            printer(f"{k}: {v}")
        printer("LUT:")
        breakpoints = list(self.lut_breakpoints().items())
        for n, (t, code) in enumerate(breakpoints):
            if n != 0:
                window = f"from {t}°C"
            elif len(breakpoints) > 1:
                window = f"below {breakpoints[1][0]}°C"
            else:
                window = "any"
            printer(f"  {window:>14}: {self.duty_format(code)}")
        image = self.image()
        for addr in range(0, self.SIZE, 16):
            printer(f"{addr:02x}: {image[addr:addr+16].hex()}")

@i2c.Interface.db.register("max31760")
class Max31760(i2c.Slave):
    ROW_SIZE = 8
    READ_SIZE = 16
    EEX_LOAD = 0x80
    EEX_ALL_BLOCKS = 0x1f
    tW = 550e-3

    def __init__(self, bus, saddr = 0x50):
        super().__init__(bus, "max31760", saddr)

    def write(self, addr, data):
        """
        Writes registers, a single transaction cannot cross an 8-byte
        row boundary.
        """
        assert addr // self.ROW_SIZE == (addr + len(data) - 1) // self.ROW_SIZE
        super().write(bytes([addr]) + data)

    def read(self, addr, size):
        return super().write_read(bytes([addr]), size)

    def status_get(self):
        return Status(self.read(Max31760Register.SR, 1)[0])

    def eeprom_get(self):
        """
        Loads EEPROM to registers and returns their contents.
        """
        self.write(Max31760Register.EEX, bytes([self.EEX_LOAD | self.EEX_ALL_BLOCKS]))
        image = b"".join(self.read(addr, self.READ_SIZE)
                         for addr in range(0, Max31760Eeprom.SIZE, self.READ_SIZE))
        self.logger.debug("EEPROM > %s", image.hex())
        return image

    def eeprom_set(self, image):
        """
        Writes registers from image, then commits them to EEPROM.
        """
        assert len(image) == Max31760Eeprom.SIZE
        self.logger.debug("EEPROM < %s", image.hex())
        for addr in range(0, Max31760Eeprom.SIZE, self.ROW_SIZE):
            self.write(addr, image[addr:addr+self.ROW_SIZE])
        self.write(Max31760Register.EEX, bytes([self.EEX_ALL_BLOCKS]))
        time.sleep(self.tW)
