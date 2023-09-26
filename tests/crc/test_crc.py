from crobe.util.crc import Crc
import unittest
from crobe.util.bytes_ops import xor_
from pathlib import Path

local_dir = Path(__file__).parent

class CrcTest(unittest.TestCase):
    def test_zlib(self):
        import zlib
        zlib_alg = Crc.from_name("zlib")

        self.assertEqual(zlib_alg.calc(b"0123456789", 0xdeadbeef), zlib.crc32(b"0123456789", 0xdeadbeef))
        self.assertEqual(zlib_alg.calc(b"0123456789"), zlib.crc32(b"0123456789"))

    def test_bluetooth(self):
        ble_chk = Crc.from_name("bluetooth_crc24")

        ble_chk_state = ble_chk()
        payload = bytes.fromhex("27104a49aeadacabaaa9bcead60507090b0d")
        ble_chk_state.update(payload)
        self.assertTrue(ble_chk.is_valid(payload + bytes(ble_chk_state)))
        
    def test_ethernet(self):
        ethernet_fcs = Crc.from_name("ethernet_fcs")

        ethernet_frame = bytes.fromhex("20cf301acea16238e0c2bd30080600010800060400016238e0c2bd300a2a2a010000000000000a2a2a0200000000000000000000000000000000000022b72660")
        ethernet_fcs_state = ethernet_fcs()
        ethernet_fcs_state.update(ethernet_frame[:-4])
        ethernet_fcs_value = bytes(ethernet_fcs_state)
        self.assertEqual(ethernet_fcs_value, ethernet_frame[-4:])
        self.assertTrue(ethernet_fcs.is_valid(ethernet_frame))
        
    def test_14443a(self):
        alg = Crc.from_name("iso14443a")

        # From ISO-Std-14443-3:2007
        with_crc = alg.append_to(b"\x00\x00")
        self.assertEqual(with_crc, b"\x00\x00\xa0\x1e")

        with_crc = alg.append_to(b"\x12\x34")
        self.assertEqual(with_crc, b"\x12\x34\x26\xcf")
        
    def test_14443b(self):
        alg = Crc.from_name("iso14443b")

        # From ISO-Std-14443-3:2007
        value = alg.append_to(b"\x00\x00\x00")
        self.assertEqual(value, b"\x00\x00\x00\xcc\xc6")

        value = alg.append_to(b"\x0f\xaa\xff")
        self.assertEqual(value, b"\x0f\xaa\xff\xfc\xd1")

        value = alg.append_to(b"\x0a\x12\x34\x56")
        self.assertEqual(value, b"\x0a\x12\x34\x56\x2c\xf6")
        
    def test_1wire(self):
        alg = Crc.from_name("one_wire")

        self.assertEqual(alg.calc(bytes.fromhex("1050a90a020800")), 0x37)
        self.assertTrue(alg.is_valid(bytes.fromhex("1050a90a02080037")))
        
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

        from crobe.component.atmel.ataes132a import crc16

        self.assertEqual(from_datasheet(b"012345678", 0), crc16.calc(b"012345678", 0))
        self.assertEqual(from_datasheet(b"012345678", 0x1234), crc16.calc(b"012345678", 0x1234))
        self.assertTrue(crc16.is_valid(bytes.fromhex("09020200000000f960")))

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

        from crobe.component.atmel.atsec import crc16

        self.assertEqual(from_datasheet(b"012345678", 0), crc16.calc(b"012345678", 0))
        self.assertEqual(from_datasheet(b"012345678", 0x1234), crc16.calc(b"012345678", 0x1234))

class PatchTests(unittest.TestCase):
    # Synthetic algorithm to test complemented input and funny init values
    stupid_alg = Crc(
        poly = 0x104c11db7,
        init = 0x055555555,
        pop_lsb = True,
        order0_at_lsb = False,
        complement_input = True,
        complement_state = True,
        spill_bitswap = True,
        spill_byte_order = "little")

    all_algs = [
        Crc.from_name("zlib"),
        Crc.from_name("ethernet_fcs"),
        Crc.from_name("bluetooth_crc24"),
        Crc.from_name("hdlc"),
        stupid_alg,
    ]
    def test_patch(self):
        original_payload = bytes.fromhex("10f9c510cecccb70a9dee996e074e2cfbb7120a590b568c808c106f3636b7015")
        change_offset = 8
        change_data = bytes.fromhex("c334993b")
        patch_offset = 14

        for alg in self.all_algs:
            original_crc = alg.update(alg.init, original_payload)

            changed_payload = original_payload[:change_offset] + change_data + original_payload[change_offset+len(change_data):]
            changed_payload_crc = alg.update(alg.init, changed_payload)

            self.assertNotEqual(original_crc, changed_payload_crc)

            data_diff = xor_(original_payload[change_offset : change_offset+len(change_data)],
                             changed_payload[change_offset : change_offset+len(change_data)])

            for patch_offset in [1, 14]:
                patch_delta = alg.data_mod_data_delta_compute(
                    change_offset,
                    data_diff,
                    patch_offset)

                patch_data = xor_(patch_delta, original_payload[patch_offset : patch_offset+len(patch_delta)])
                fixed_payload = changed_payload[:patch_offset] + patch_data + changed_payload[patch_offset+len(patch_data):]

                fixed_payload_crc = alg.update(alg.init, fixed_payload)

                self.assertEqual(original_crc, fixed_payload_crc, f"{alg}")

class AlgSerializationTest(unittest.TestCase):
    def test_save_restore(self):
        for _, alg in Crc.algorithms():
            self.assertEqual(alg, Crc.from_desc_string(str(alg)))

class RevengTest(unittest.TestCase):
    def test_save_restore(self):
        filename = local_dir / "crc_list.txt"
        ignore_count = 0
        with open(filename, "r") as fd:
            for line in fd.readlines():
                line = line.strip()
                if line.startswith("#"):
                    continue

                if not line:
                    continue

                try:
                    alg = Crc.from_reveng(line)
                except NotImplementedError:
                    #print(line, "Ignored")
                    ignore_count += 1
                    continue

                check = alg.calc(b"123456789")
                self.assertEqual(alg._reveng_check, check, f"While testing {alg._reveng_name}: {repr(alg)}")
                without_name = " ".join(line.split()[:-1])
                self.assertEqual(without_name, alg.reveng_string)

        self.assertEqual(ignore_count, 3)
