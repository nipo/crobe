from crobe.util.crc import Crc
import unittest

class CrcTest(unittest.TestCase):
    def test_zlib(self):
        import zlib
        zlib_alg = Crc.zlib

        self.assertEqual(zlib_alg.calc(b"0123456789", 0xdeadbeef), zlib.crc32(b"0123456789", 0xdeadbeef))
        self.assertEqual(zlib_alg.calc(b"0123456789"), zlib.crc32(b"0123456789"))

    def test_bluetooth(self):
        ble_chk = Crc.bluetooth_crc24
        ble_chk_state = ble_chk()
        payload = bytes.fromhex("27104a49aeadacabaaa9bcead60507090b0d")
        ble_chk_state.update(payload)
        self.assertTrue(ble_chk.is_valid(payload + bytes(ble_chk_state)))
        
    def test_ethernet(self):
        ethernet_frame = bytes.fromhex("20cf301acea16238e0c2bd30080600010800060400016238e0c2bd300a2a2a010000000000000a2a2a0200000000000000000000000000000000000022b72660")
        ethernet_fcs = Crc.ethernet_fcs
        ethernet_fcs_state = ethernet_fcs()
        ethernet_fcs_state.update(ethernet_frame[:-4])
        ethernet_fcs_value = bytes(ethernet_fcs_state)
        self.assertEqual(ethernet_fcs_value, ethernet_frame[-4:])
        self.assertTrue(ethernet_fcs.is_valid(ethernet_frame))
        
    def test_14443a(self):
        # From ISO-Std-14443-3:2007
        with_crc = Crc.iso14443a.append_to(b"\x00\x00")
        self.assertEqual(with_crc, b"\x00\x00\xa0\x1e")

        with_crc = Crc.iso14443a.append_to(b"\x12\x34")
        self.assertEqual(with_crc, b"\x12\x34\x26\xcf")
        
    def test_14443b(self):
        # From ISO-Std-14443-3:2007
        value = Crc.iso14443b.append_to(b"\x00\x00\x00")
        self.assertEqual(value, b"\x00\x00\x00\xcc\xc6")

        value = Crc.iso14443b.append_to(b"\x0f\xaa\xff")
        self.assertEqual(value, b"\x0f\xaa\xff\xfc\xd1")

        value = Crc.iso14443b.append_to(b"\x0a\x12\x34\x56")
        self.assertEqual(value, b"\x0a\x12\x34\x56\x2c\xf6")
        
class AtmelCrcTest(unittest.TestCase):
    def test_ataes132a(self):
        def from_datasheet(blob, crc = 0):
            for b in blob:
                for i in range(8):
                    append = ((b >> 7) & 0x1) ^ (crc >> 15)
                    crc <<= 1
                    if append:
                        crc ^= 0x8005
                    b <<= 1
                    crc &= 0xffff
            return crc

        as_alg = Crc(width = 16, poly = 0x8005, init = 0,
                     pop_lsb = False, insert_msb = False,
                     complement_input = False, complement_state = False,
                     spill_bitswap = False, spill_byte_order = "big")

        self.assertEqual(from_datasheet(b"012345678", 0), as_alg.calc(b"012345678", 0))
        self.assertEqual(from_datasheet(b"012345678", 0x1234), as_alg.calc(b"012345678", 0x1234))
        self.assertTrue(as_alg.is_valid(bytes.fromhex("09020200000000f960")))

    def test_ataecc(self):
        # Atmel CryptoAuthentication Data Zone CRC Calculation APPLICATION NOTE
        def from_datasheet(blob, crc = 0):
            for b in blob:
                for i in range(8):
                    append = (b & 0x1) ^ (crc >> 15)
                    crc <<= 1
                    if append:
                        crc ^= 0x8005
                    b >>= 1
                    crc &= 0xffff
            return crc

        as_alg = Crc(width = 16, poly = 0x8005, init = 0,
                     pop_lsb = True, insert_msb = False,
                     complement_input = False, complement_state = False,
                     spill_bitswap = False, spill_byte_order = "little")

        self.assertEqual(from_datasheet(b"012345678", 0), as_alg.calc(b"012345678", 0))
        self.assertEqual(from_datasheet(b"012345678", 0x1234), as_alg.calc(b"012345678", 0x1234))
        
class OneWireCrcTest(unittest.TestCase):
    def test_1wire(self):
        self.assertEqual(Crc.one_wire.calc(bytes.fromhex("1050a90a020800")), 0x37)
        self.assertTrue(Crc.one_wire.is_valid(bytes.fromhex("1050a90a02080037")))
