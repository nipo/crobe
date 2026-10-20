from crobe.component.st.stusb4500 import StUsb4500Nvm, GpioCfg
import unittest

class StUsb4500NvmTest(unittest.TestCase):
    SECTORS_12V_2A = [
        bytes.fromhex("0000b0ab00450000"),
        bytes.fromhex("20409c1cff013cdf"),
        bytes.fromhex("02400f003200fcf1"),
        bytes.fromhex("001915aff7355f00"),
        bytes.fromhex("003c9021430040fb"),
        ]

    def test_roundtrip(self):
        for sectors in (StUsb4500Nvm.DEFAULT, self.SECTORS_12V_2A):
            nvm = StUsb4500Nvm(sectors)
            self.assertEqual(nvm.sectors(), list(sectors))
            rebuilt = StUsb4500Nvm.from_config(nvm.to_config(), sectors)
            self.assertEqual(rebuilt.sectors(), list(sectors))

    def test_default_decode(self):
        nvm = StUsb4500Nvm()
        self.assertEqual(nvm.pdo_count, 3)
        self.assertEqual([nvm.pdo_voltage(n) for n in (1, 2, 3)], [5000, 15000, 20000])
        self.assertEqual([nvm.pdo_current(n) for n in (1, 2, 3)], [1500, 1500, 1000])
        self.assertEqual(nvm.flex_current, 2000)
        self.assertEqual(nvm.gpio_cfg, GpioCfg.ERROR_RECOVERY)

    def test_encode(self):
        config = {
            "pdo": [
                {"current": "0.5A"},
                {"voltage": "12V", "current": "2A"},
                ],
            "pdo_count": 2,
            "usb_comm_capable": True,
            "gpio_cfg": "debug",
            }
        nvm = StUsb4500Nvm.from_config(config, StUsb4500Nvm.DEFAULT)
        self.assertEqual(nvm.sectors()[1:], self.SECTORS_12V_2A[1:])

    def test_current_lut(self):
        for code in range(1, 16):
            self.assertEqual(StUsb4500Nvm.current_encode(StUsb4500Nvm.current_decode(code)), code)
        self.assertEqual(StUsb4500Nvm.current_decode(10), 2750)
        self.assertEqual(StUsb4500Nvm.current_decode(11), 3000)
        self.assertEqual(StUsb4500Nvm.current_decode(15), 5000)

    def test_quantity(self):
        self.assertEqual(StUsb4500Nvm.quantity_parse("12V", "V"), 12000)
        self.assertEqual(StUsb4500Nvm.quantity_parse("500mA", "A"), 500)
        self.assertEqual(StUsb4500Nvm.quantity_parse(1.25, "A"), 1250)
        self.assertEqual(StUsb4500Nvm.quantity_format(12050, "V"), "12.05V")

    def test_invalid(self):
        for config in (
                {"pdo": [{}, {"current": "2.1A"}]},
                {"pdo": [{}, {"voltage": "12.01V"}]},
                {"pdo": [{}, {"voltage": "21V"}]},
                {"pdo": [{"voltage": "9V"}]},
                {"pdo": [{"uvlo": 10}]},
                {"pdo_count": 0},
                {"flex_current": "2.005A"},
                {"power_ok_cfg": 1},
                {"usb_comm_capable": "yes"},
                {"gpio_cfg": "bogus"},
                {"bogus": 1},
                ):
            with self.subTest(config = config):
                with self.assertRaises(ValueError):
                    StUsb4500Nvm.from_config(config, StUsb4500Nvm.DEFAULT)

if __name__ == "__main__":
    unittest.main()
