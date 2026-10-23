from crobe.component.maxim.max31760 import Max31760Eeprom
import decimal
import unittest

class Max31760EepromTest(unittest.TestCase):
    IMAGE_25KHZ = bytes.fromhex(
        "193011ffc218500055005f004600fffe"
        + "00" * 16
        + "33" * 12 + "66" * 5 + "9a" * 5 + "cd" * 5 + "ff" * 21)

    CONFIG_25KHZ = {
        "temperature_source": "remote",
        "pwm_frequency": 25000,
        "ramp_rate": 6.25,
        "spin_up": True,
        "tach2": False,
        "mask": {"tach2": True},
        "threshold": {"remote_high": 80, "remote_overtemp": 95},
        "lut": {16: "20%", 40: "40%", 50: "60%", 60: "80%", 70: "100%"},
        }

    def test_roundtrip(self):
        odd = bytearray(self.IMAGE_25KHZ)
        odd[0x07] = 0x20
        odd[0x18:0x20] = bytes(range(8))
        for image in (Max31760Eeprom.DEFAULT, self.IMAGE_25KHZ, bytes(odd)):
            eeprom = Max31760Eeprom(image)
            self.assertEqual(eeprom.image(), image)
            rebuilt = Max31760Eeprom.from_config(eeprom.to_config(), image)
            self.assertEqual(rebuilt.image(), image)
            rebuilt = Max31760Eeprom.from_config(eeprom.to_config(), Max31760Eeprom.DEFAULT)
            self.assertEqual(rebuilt.image()[:0x18], image[:0x18])
            self.assertEqual(rebuilt.image()[0x20:], image[0x20:])

    def test_default_decode(self):
        eeprom = Max31760Eeprom()
        self.assertEqual(eeprom.temperature_source, "remote")
        self.assertEqual(eeprom.choice_get("pwm_frequency"), 33)
        self.assertEqual(eeprom.choice_get("fan_fail_mode"), "comparator")
        self.assertEqual(eeprom.ideality, decimal.Decimal("1.008"))
        self.assertEqual(eeprom.threshold("remote_overtemp"), 110)
        self.assertEqual(eeprom.threshold("local_high"), 70)
        self.assertEqual(eeprom.tach_threshold, 0xfffe)
        self.assertEqual(eeprom.lut_breakpoints(), {16: 0xff})

    def test_encode(self):
        eeprom = Max31760Eeprom.from_config(self.CONFIG_25KHZ, Max31760Eeprom.DEFAULT)
        self.assertEqual(eeprom.image(), self.IMAGE_25KHZ)

    def test_temperature_source(self):
        for source in Max31760Eeprom.TEMPERATURE_SOURCES:
            eeprom = Max31760Eeprom.from_config({"temperature_source": source}, Max31760Eeprom.DEFAULT)
            self.assertEqual(eeprom.temperature_source, source)

    def test_threshold(self):
        eeprom = Max31760Eeprom.from_config(
            {"threshold": {"local_high": -12.375}}, Max31760Eeprom.DEFAULT)
        self.assertEqual(eeprom.image()[0x0c:0x0e], bytes.fromhex("f3a0"))
        self.assertEqual(eeprom.to_config()["threshold"]["local_high"], -12.375)

    def test_duty(self):
        self.assertEqual(Max31760Eeprom.duty_parse("50%"), 0x80)
        self.assertEqual(Max31760Eeprom.duty_parse(100), 0xff)
        self.assertEqual(Max31760Eeprom.duty_parse("99.7%"), 0xff)
        self.assertEqual(Max31760Eeprom.duty_parse(0), 0)
        for code in range(256):
            self.assertEqual(Max31760Eeprom.duty_parse(Max31760Eeprom.duty_format(code)), code)

    def test_ideality(self):
        for code, value in enumerate(Max31760Eeprom.IDEALITY):
            eeprom = Max31760Eeprom.from_config({"ideality": float(value)}, Max31760Eeprom.DEFAULT)
            self.assertEqual(eeprom.ifr, code)

    def test_invalid(self):
        for config in (
                {"temperature_source": "both"},
                {"pwm_frequency": 100},
                {"hysteresis": True},
                {"ramp_rate": "fast"},
                {"spin_up": "yes"},
                {"fan_fail_duty": "101%"},
                {"fan_fail_duty": "half"},
                {"tach_threshold": 0x10000},
                {"tach_threshold": 1.5},
                {"ideality": 1.0085},
                {"mask": {"bogus": True}},
                {"mask": {"tach1": 1}},
                {"threshold": {"local_high": 70.1}},
                {"threshold": {"local_high": 128}},
                {"threshold": []},
                {"user": "00"},
                {"user": "zz"},
                {"lut": {18: "50%"}},
                {"lut": {16: "50%", 17: "60%"}},
                {"lut": {16: "50%", 112: "60%"}},
                {"lut": [1, 2]},
                {"bogus": 1},
                ):
            with self.subTest(config = config):
                with self.assertRaises(ValueError):
                    Max31760Eeprom.from_config(config, Max31760Eeprom.DEFAULT)

    def test_invalid_image(self):
        for addr, value in ((0x00, 0x41), (0x02, 0x83), (0x05, 0x40)):
            image = bytearray(Max31760Eeprom.DEFAULT)
            image[addr] = value
            with self.subTest(addr = addr):
                with self.assertRaises(ValueError):
                    Max31760Eeprom(bytes(image))
        with self.assertRaises(ValueError):
            Max31760Eeprom(Max31760Eeprom.DEFAULT[:-1])

if __name__ == "__main__":
    unittest.main()
