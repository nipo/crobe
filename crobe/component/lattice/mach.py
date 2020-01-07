from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag, spi, i2c
from ... import bitfield
from ...util.endian import bitswap8
import struct
from ... import bitstring
from . import bitstream, parts, opcodes
import datetime
import time
import binascii

class MachXO2Config:
    ENABLE_ARG = b'\x08\x00\x00'
    DISABLE_ARG = b'\x00\x00'

    ERASE_SRAM = 1
    ERASE_FEATURE = 2
    ERASE_FLASH = 4
    ERASE_UFM = 8

    class Status(bitfield.Register):
        name = "Status"
        fields = [
            bitfield.BinaryField("Transparent mode", 0, "No", "Yes"),
            bitfield.Field("Target", (1, 3), {0: "SRAM", 1: "EFUSE", 2: "Feature", 4:"Flash"}),
            bitfield.EnableField("JTAG", 4),
            bitfield.BinaryField("Logic is pw prot.", 5, "No", "Yes"),
            bitfield.EnableField("SRAM OTP", 6),
            bitfield.EnableField("Decrypt", 7),
            bitfield.BinaryField("Done", 8, "No", "Yes"),
            bitfield.EnableField("ISC", 9),
            bitfield.EnableField("Write", 10),
            bitfield.EnableField("Read", 11),
            bitfield.BinaryField("Busy", 12, "No", "Yes"),
            bitfield.BinaryField("Fail", 13, "No", "Yes"),
            bitfield.BinaryField("Feature OTP", 14, "No", "Yes"),
            bitfield.BinaryField("Decrypt only", 15, "No", "Yes"),
            bitfield.EnableField("Passw prot.", 16),
            bitfield.EnableField("UFM OTP", 17),
            bitfield.EnableField("Assp", 18),
            bitfield.EnableField("Sdmen", 19),
            bitfield.BinaryField("Enc. preamble", 20, "none", "detected"),
            bitfield.BinaryField("Std. Pream", 21, "none", "detected"),
            bitfield.BinaryField("SPI", 22, "OK", "Fail"),
            bitfield.Field("Error", (23, 25), ["OK", "ID", "Bad command", "CRC", "Preamble", "Abort", "Overflow", "SRAM ovr."]),
            bitfield.BinaryField("Execution error", 26, "No", "Yes"),
            bitfield.BinaryField("ID Mismatch", 27, "No", "Yes"),
            bitfield.BinaryField("Invalid Command", 28, "No", "Yes"),
            bitfield.BinaryField("SED Error", 29, "No", "Yes"),
            bitfield.BinaryField("Bypass", 30, "No", "Yes"),
            bitfield.BinaryField("Flow through mode", 31, "No", "Yes"),
            ]

    class Ctrl0(bitfield.Register):
        name = "Control 0"
        fields = [
            bitfield.ValueField("Master clock Freq", (0, 5)),
            bitfield.ValueField("SPI Mode", (6, 7)),
            bitfield.BinaryField("SPI bit order", 8, "MSB First", "LSB First"),
            bitfield.ValueField("MCLKB", 9),
            bitfield.ValueField("STX DUM", (10, 11)),
            bitfield.ValueField("DONE", (12, 14)),
            bitfield.ValueField("INIT", (15, 17)),
            bitfield.ValueField("P_DONE", (18, 19)),
            bitfield.EnableField("SPI Master", 20),
            bitfield.EnableField("SPI Slave Slow Respond Mode", 21),
            bitfield.BinaryField("CPU Mon", 22, "No", "Yes"),
            bitfield.BinaryField("SSPI Auto", 23, "No", "Yes"),
            bitfield.BinaryField("HFC", 24, "No", "Yes"),
            bitfield.BinaryField("TranEdit", 25, "No", "Yes"),
            bitfield.DisableField("CDM", 26),
            bitfield.DisableField("BKE", 27),
            bitfield.BinaryField("NDR", 28, "No", "Yes"),
            bitfield.BinaryField("Wake Up", 29, "No", "Yes"),
            bitfield.ValueField("Core clock sel", (30, 31)),
            ]

    class Feature(bitfield.Register):
        name = "Feature"
        fields = [
            bitfield.ValueField("IDCODE", (0, 31)),
            bitfield.ValueField("TRACEID", (32, 39)),
            bitfield.ValueField("I2C Addr", (40, 47)),
            bitfield.EnableField("Secpwd",  48),
            bitfield.EnableField("Deconly",  49),
            bitfield.EnableField("Pwdflash",  50),
            bitfield.EnableField("Pwdall",  51),
            bitfield.EnableField("Myassp",  52),
            bitfield.EnableField("Program",  53),
            bitfield.EnableField("Init",  54),
            bitfield.EnableField("Done",  55),
            bitfield.EnableField("Jtag",  56),
            bitfield.EnableField("Sspi",  57),
            bitfield.EnableField("I2c",  58),
            bitfield.EnableField("Mspi",  59),
            bitfield.EnableField("Boots1",  60),
            bitfield.EnableField("Boots2",  61),
            bitfield.EnableField("Rsvd",  62),
            ]

    class TraceId(bitfield.Register):
        name = "TraceId"
        fields = [
            bitfield.ValueField("User", (56, 63)),
            bitfield.ValueField("Lot", (24, 55)),
            bitfield.ValueField("Wafer", (19, 23)),
            bitfield.ValueField("X", (12, 18)),
            bitfield.ValueField("Y", (5, 11)),
            bitfield.ValueField("Spare", (0, 4)),
            ]

    def __init__(self):
        pass

    @property
    def idcode(self):
        return int.from_bytes(self.cmd(opcodes.IDCODE, None, 4), "big")

    def start(self):
        idcode = self.idcode
        possible_parts = [p for p in parts.PARTS if int(idcode) == p.idcode]
        if len(possible_parts) > 1:
            suffixes = [p.name.split("-", 1)[1] for p in possible_parts]
            prefix = possible_parts[0].name.split("-", 1)[0]
            self.name = prefix + "-" + "/".join(suffixes)
            self.info = possible_parts[0]
        else:
            self.info = possible_parts[0]
            self.name = self.info.name

        self.config_memory_size = self.info.row_count * self.info.col_bit_count // 8
        self.flash_size = (self.info.flash_page_count + self.info.ufm_page_count) * 16
        self.__bg_enable = None

        self.logger.info("Found %s", self.info.name)

        self.uid = int.from_bytes(self.cmd(opcodes.LSC_UIDCODE_PUB, None, 8), "big")
        self.logger.info("UID: 0x%08x", self.uid)
        self.TraceId(self.uid).dump(self.logger.info)

        self._isc_enable(True)
        self.Status(self.status).dump(self.logger.info)
        self.Feature(self.feature).dump(self.logger.info)
        self._isc_disable()

        #jtag.Tap.start(self)

    def _isc_enable(self, background = None):
        if self.__bg_enable is None and background is None:
            raise ValueError("Cannot reenable with no previous enable")
        if background is None:
            background = self.__bg_enable

#        self.cmd(opcodes.ISC_DISABLE, self.DISABLE_ARG)
#        self.wait_no_fail()
        self.cmd(opcodes.LSC_ENABLE_X if background else opcodes.ISC_ENABLE, self.ENABLE_ARG)
        self.wait_no_fail()
        self.__bg_enable = background

        self.status_check(0, 0x0200)

    def _isc_disable(self):
        self.cmd(opcodes.ISC_DISABLE, self.DISABLE_ARG)
        self.run(10000)
#        self.status_check(0x3200, 0)
#        self.cmd(opcodes.BYPASS, None)
        self.__bg_enable = None

    @property
    def done(self):
        return self.ir_status & 0x84 == 0x04

    def _bypass(self):
        self.cmd(opcodes.BYPASS, None)
        self.run(100)

    def _addr_set(self, addr = None):
        pass

    def _erase(self, what):
        assert self.__bg_enable is not None
        self.cmd(opcodes.ISC_ERASE, bytes([what, 0, 0]))
        self._addr_set(None)
        for retry in range(4):
            try:
                self._isc_enable()
                self.wait_no_fail()
            except:
                time.sleep(.5)
                if retry == 3:
                    raise

    def _stop(self):
        self._erase(self.ERASE_SRAM)
        self.__bg_enable = None

    def stop(self):
        self._isc_enable(False)
        self._stop()
        self._isc_disable()

    def _erase_all(self):
        self._erase(self.ERASE_SRAM | self.ERASE_UFM | self.ERASE_FLASH | self.ERASE_FEATURE)

    def erase_all(self):
        self._isc_enable(False)
        self._erase_all()
        self._isc_disable()

    def refresh(self):
        self._isc_enable(True)
        self._refresh()
        self._isc_disable()

    @property
    def status(self):
        return int.from_bytes(self.cmd(opcodes.LSC_READ_STATUS, None, 4), 'big')

    @property
    def feature(self):
        return int.from_bytes(self.cmd(opcodes.LSC_READ_FEATURE, None, 8), 'big')

    @property
    def busy(self):
        return self.cmd(opcodes.LSC_CHECK_BUSY, None, 1)[0]

    def status_check(self, expect_clear, expect_set):
        mask = expect_set | expect_clear
        status = self.status
        if status & mask == expect_set:
            return
        self.Status(status).dump(self.logger.error)
        raise ValueError("Expected status with 0x%08x set, 0x%08x clear, got 0x%08x" %
                         (expect_set, expect_clear, status))

    def wait_idle(self, timeout = 1.):
        step = .01

        for i in range(max(int(timeout / step), 1)):
            self.run(1)
            b = self.busy
            if b == 0:
                return
            time.sleep(.01)

        raise RuntimeError("Busy flag stuck", b)

    def wait_no_fail(self, timeout = 1.):
        self.wait_idle(timeout)
        self.status_check(3 << 12, 0)

    def _flash_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_FLASH)

    def _ufm_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_UFM)

    def _feature_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_FEATURE)

    def _flash_read(self, offset, size):
        return self._mem_read(offset, size, opcodes.LSC_INIT_ADDRESS, 0)

    def _ufm_read(self, offset, size):
        return self._mem_read(offset, size, opcodes.LSC_INIT_ADDRESS_UFM, 0x40000000)

    def _mem_read(self, offset, size, addr_init, offset_base):
        assert self.__bg_enable is not None
        self.status_check(0, 0xa00)

        self.cmd(addr_init, bytes([offset_base >> 28, 0, 0]))
        self.wait_no_fail()

#        self.cmd(opcodes.LSC_READ_INCR_NV, b'\x00\x00\x01', 16),

        data = b''
        for addr in range(offset & ~0xf, offset + size, 16):
            self.cmd(opcodes.LSC_WRITE_ADDRESS, None,
                     (offset_base + (addr + offset) // 16).to_bytes(4, "big"))
            self.wait_no_fail()

            r = self.cmd(opcodes.LSC_READ_INCR_NV, b'\x00\x00\x01', 16)[-16:]

            row_count = ((offset & 0xf) + size + 0xf) // 16
            data += r

#        data = self.row_flip(data)

        return data[offset & 0xf : (offset & 0xf) + size]

    def _mem_write(self, offset, data, addr_init, offset_base):
#        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        if offset % 16:
            prelen = (-offset % 16)
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            offset = offset & ~0xf

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.cmd(addr_init, b"\x00\x00\x00")
        self.run(1)
        self.wait_no_fail()

        if offset:
            self.cmd(opcodes.LSC_WRITE_ADDRESS, offset_base + offset // 16, 32)
            self.run(1)
            self.wait_no_fail()

#        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.cmd(opcodes.LSC_PROG_INCR_NV, None, bytes(data[off : off+16]))
            assert not self.wait_no_fail()

    def _flash_write(self, offset, data):
        return self._mem_write(offset, data, opcodes.LSC_INIT_ADDRESS, 0x20000000)

    def _ufm_write(self, offset, data):
        return self._mem_write(offset, data, opcodes.LSC_INIT_ADDRESS_UFM, 0x40000000)

    def lol(self):
        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        #self.logger.info("Flash write 0x%08x %d", offset, len(data))
        if offset:# % 16:
            #prelen = (-offset % 16)
            prelen = offset
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            #offset = offset & ~0xf
            offset = 0

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.dr_shift(opcodes.LSC_INIT_ADDRESS, 4, 8)
        self.wait_no_fail()

        #self.dr_shift(opcodes.LSC_WRITE_ADDRESS, offset // 16, 32)
        #self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.dr_shift(opcodes.LSC_PROG_INCR_NV,
                          bytes(data[off : off+16]),
                          read_tdo = False)
            assert not self.wait_no_fail()

    def _flash_done_set(self):
        self.cmd(opcodes.ISC_PROGRAM_DONE, None)
        self.run(20000)

    def flash_erase(self):
        self._isc_enable(True)
        self._flash_erase()
        self._isc_disable()

    def ufm_erase(self):
        self._isc_enable(True)
        self._ufm_erase()
        self._isc_disable()

    def flash_read(self, offset, size):
        self._isc_enable(False)
        ret = self._flash_read(offset, size)
        self._isc_disable()
        return ret

    def ufm_read(self, offset, size):
        self._isc_enable(False)
        ret = self._ufm_read(offset, size)
        self._isc_disable()
        return ret

    def flash_write(self, offset, data):
        self._isc_enable(False)
        self._flash_write(offset, data)
        self._isc_disable()

    def ufm_write(self, offset, data):
        self._isc_enable(True)
        self._ufm_write(offset, data)
        self._isc_disable()

    def _feature_read(self):
        return bytes(self.cmd(opcodes.LSC_READ_FEATURE, None, 8))

    def _feabits_read(self):
        return bytes(self.cmd(opcodes.LSC_READ_FEABITS, None, 2))

    def feature_read(self):
        self._isc_enable(True)
        ret = self._feature_read(self)
        self._isc_disable()
        return ret

    def feabits_read(self):
        self._isc_enable(True)
        ret = self._feabits_read(self)
        self._isc_disable()
        return ret

    def _feature_write(self, feature):
        self.dr_shift(opcodes.LSC_INIT_ADDRESS, 0x02, 8)
        self.run(1000)

        self.dr_shift(opcodes.LSC_PROG_FEATURE, bytes(feature))
        self.run(1000)

    def _feabits_write(self, feabits):
        self.dr_shift(opcodes.LSC_PROG_FEABITS, bytes(feabits))
        self.run(1000)

    @staticmethod
    def row_flip(data):
        assert len(data) % 16 == 0
        tmp = b""
        for offset in range(0, len(data), 16):
            tmp += bitswap8(data[offset : offset + 16])
        return tmp

    def _refresh(self):
        for retry in range(5):
            self.cmd(opcodes.LSC_REFRESH, None)
            self._assert_done()
        self.wait_no_fail(5)

    def _assert_done(self):
        self.wait_idle(10)
        self.status_check(0x2000, 0x100)

    def cmd(self, op, args, data = None):
        raise NotImplementedError()

    def _usercode_write(self, uc):
        self.cmd(opcodes.ISC_PROGRAM_USERCODE, None, uc.to_bytes(4, "big"))

@jtag.Tap.db.register(*set([PartId.from_idcode(p.idcode).drop_revision() for p in parts.PARTS]))
class MachXO2(jtag.Tap, MachXO2Config):
    irlen = 8
    max_freq = 25e6
    ENABLE_ARG = 0x08
    
    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        matches = [p for p in parts.PARTS if int(port.idcode_at(index).drop_revision()) == p.idcode]
        if len(matches) > 1:
            suffixes = [p.name.split("-", 1)[1] for p in matches]
            prefix = matches[0].name.split("-", 1)[0]

            self.name = prefix + "-" + "/".join(suffixes)
        else:
            self.name = self.info.name
        self.info = matches[0]
        self.config_memory_size = self.info.row_count * self.info.col_bit_count // 8
        self.flash_size = (self.info.flash_page_count + self.info.ufm_page_count) * 16
        self.__bg_enable = None

    def start(self):
        self.uid = int.from_bytes(self.cmd(opcodes.LSC_UIDCODE_PUB, None, 8), "big")
        self.logger.info("UID: 0x%08x", self.uid)
        self.TraceId(self.uid).dump(self.logger.info)

        try:
            self._isc_enable(True)
            self.Status(self.status).dump(self.logger.info)
            self.Feature(self.feature).dump(self.logger.info)
            self._isc_disable()
        except:
            pass
            
        jtag.Tap.start(self)

    def _isc_enable(self, background = None, arg = None):
        if self.__bg_enable is None and background is None:
            raise ValueError("Cannot reenable with no previous enable")
        #if background is None:
        #    background = self.__bg_enable

        self.dr_shift(opcodes.ISC_DISABLE, None)
        self.wait_no_fail()
        self.dr_shift(opcodes.LSC_ENABLE_X if background else opcodes.ISC_ENABLE,
                      arg if arg is not None else self.ENABLE_ARG, 8)
        self.wait_no_fail()
        self.__bg_enable = background

        self.status_check(0, 0x0200)

    def _isc_disable(self):
        self.dr_shift(opcodes.ISC_DISABLE, None)
        self.wait_no_fail()
        self.__bg_enable = None

    def _erase(self, what):
        assert self.__bg_enable is not None
        self.dr_shift(opcodes.ISC_ERASE, what, 8)
        self.run(1)
        self.wait_no_fail(10)

    @property
    def status(self):
        return self.dr_shift(opcodes.LSC_READ_STATUS, 0, 32, read_tdo = True)

    @property
    def feature(self):
        return self.dr_shift(opcodes.LSC_READ_FEATURE, 0, 64, read_tdo = True)

    @property
    def feabits(self):
        return self.dr_shift(opcodes.LSC_READ_FEABITS, 0, 16, read_tdo = True)

    def cmd(self, op, args, data = None):
        self.logger.debug("CMD %02x", op)
        if args and data:
            raise NotImplementedError()
        if args is None and isinstance(data, int):
            return self.dr_shift(op, b'\x00' * data, read_tdo = True)
        if args is None and isinstance(data, bytes):
            self.dr_shift(op, data, read_tdo = False)
            self.run()
            return
        if data is None:
            self.dr_shift(op, args or None, read_tdo = False)
            self.run()
            return
        raise NotImplementedError()

    def _mem_read(self, offset, size, addr_init, offset_base):
        assert self.__bg_enable is not None
        self.status_check(0, 0xa00)

        self.dr_shift(addr_init, offset_base >> 28, 8)
        self.run(1)
        self.wait_no_fail()

        self.dr_shift(opcodes.LSC_WRITE_ADDRESS, offset_base + offset // 16, 32)
        self.run(1)
        self.wait_no_fail()

        cmds = [
            self.cmd_dr_shift(opcodes.LSC_READ_INCR_NV, None),
            self.run(10),
            self.cmd_dr_shift(None, None,
                            16 * 8,
                            read_tdo = True,
                            return_type = bytes),
            ]
        self.execute(cmds)

        data = b''
        for addr in range(offset & ~0xf, offset + size, 16):
            cmds = [
                self.cmd_dr_shift(opcodes.LSC_READ_INCR_NV, None),
                self.run(10),
                self.cmd_dr_shift(None, None,
                                16 * 8,
                                read_tdo = True,
                                return_type = bytes),
                ]
            self.execute(cmds)

            row_count = ((offset & 0xf) + size + 0xf) // 16
            data += cmds[2].tdo

        data = self.row_flip(data)

        return data[offset & 0xf : (offset & 0xf) + size]

    def _mem_write(self, offset, data, addr_init, offset_base):
#        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        if offset % 16:
            prelen = (-offset % 16)
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            offset = offset & ~0xf

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.dr_shift(addr_init, 4, 8)
        self.run(1)
        self.wait_no_fail()

        if offset:
            self.dr_shift(opcodes.LSC_WRITE_ADDRESS, offset_base + offset // 16, 32)
            self.run(1)
            self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.execute([
                self.cmd_dr_shift(opcodes.LSC_PROG_INCR_NV, None),
                self.cmd_dr_shift(None, bytes(data[off : off+16]), read_tdo = False),
                ])
            assert not self.wait_no_fail()

    def _flash_write(self, offset, data):
        return self._mem_write(offset, data, opcodes.LSC_INIT_ADDRESS, 0)

    def lol(self):
        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        #self.logger.info("Flash write 0x%08x %d", offset, len(data))
        if offset:# % 16:
            #prelen = (-offset % 16)
            prelen = offset
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            #offset = offset & ~0xf
            offset = 0

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.dr_shift(opcodes.LSC_INIT_ADDRESS, 4, 8)
        self.wait_no_fail()

        #self.dr_shift(opcodes.LSC_WRITE_ADDRESS, offset // 16, 32)
        #self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.dr_shift(opcodes.LSC_PROG_INCR_NV,
                          bytes(data[off : off+16]),
                          read_tdo = False)
            assert not self.wait_no_fail()

    def feature_read(self):
        self._isc_enable(True)
        ret = self.dr_shift(opcodes.LSC_READ_FEATURE, None, 64, read_tdo = True, return_type = bytes)
        self._isc_disable()
        return ret

    def feabits_read(self):
        self._isc_enable(True)
        ret = self.dr_shift(opcodes.LSC_READ_FEABITS, None, 16, read_tdo = True, return_type = bytes)
        self._isc_disable()
        return ret

    def load(self, config):
        from ...loadable.object import Program

        assert isinstance(config, Program)
        bs = bitstream.Bitstream(parts.PARTS, config)
        
        self.ram_load(bs)

    def ram_load(self, bs):
        assert self.idcode.is_same_part(PartId.from_idcode(bs.info.idcode))
        self._isc_enable(False, 0)
        self._erase(self.ERASE_SRAM)

        bs_cmds = [
            self.cmd_dr_shift(opcodes.LSC_PROG_CTRL0, 0x40000000, 32),
            self.cmd_run(10),
            self.cmd_dr_shift(opcodes.LSC_INIT_ADDRESS, 0, 8),
            self.cmd_run(10),
        ]

        for frame in bs.rti:
            data = frame.data
            data = bitswap8(data)
            bs_cmds.extend([
                self.cmd_dr_shift(opcodes.LSC_PROG_INCR_RTI, bytes(data)),
                self.cmd_run(10),
            ])

        bs_cmds.extend([
            self.cmd_dr_shift(opcodes.USERCODE, 0, 32),
            self.cmd_dr_shift(opcodes.ISC_PROGRAM_USERCODE, None),
            self.cmd_run(100),
            self.cmd_dr_shift(opcodes.ISC_PROGRAM_DONE, None),
            self.cmd_run(100),
            self.cmd_dr_shift(opcodes.BYPASS, None),
        ])

        self.execute(bs_cmds)

        self._isc_disable()
        
        self.dr_shift(opcodes.BYPASS, None)
        self.run(1)
        
@i2c.Interface.db.register("machxo2")
class MachXO2I2c(PortComponent, MachXO2Config):
    ENABLE_ARG = b'\x08\x00'
    DISABLE_ARG = b'\x00\x00'
    
    def __init__(self, bus):
        PortComponent.__init__(self, bus, "MachXO2")
        MachXO2Config.__init__(self)
        self.saddr = None

    def start(self):
        assert self.saddr is not None
        MachXO2Config.start(self)

    def _addr_set(self, addr = None):
        time.sleep(.5)
        self.saddr = 0x40 if addr is None else addr

    def cmd(self, op, args, data = None):
        self.logger.info("CMD %02x", op)
        if args is None:
            args = b'\x00\x00\x00'
            if op in [0x74, 0xc6]:
                args = b'\x08\x00'
        cmd = bytes([op]) + args
        for i in range(10, -1, -1):
            try:
                if isinstance(data, int) and data:
                    return self.port.write_read(self.saddr, cmd, data)
                else:
                    return self.port.write(self.saddr, cmd + (data or b''))
            except i2c.AddressNack:
                if not i:
                    raise
            time.sleep(.001)

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
        else:
            return PortComponent.option_set(opt)

    def run(self, cycles):
        self.cmd(0xff, None)
        if cycles > 1000:
            time.sleep(.5)

    def _feature_write(self, feature):
        self.status_check(0, 0x0200)
        self.cmd(opcodes.LSC_PROG_FEATURE, None, bytes(feature)[::-1])
        self._addr_set(bytes(feature)[5] * 4)
        self.wait_no_fail()

    def _feabits_write(self, feabits):
        self.status_check(0, 0x0200)
        self.cmd(opcodes.LSC_PROG_FEABITS, None, bytes(feabits)[::-1])
        self.wait_no_fail()

    def _feature_read(self):
        return bytes(self.cmd(opcodes.LSC_READ_FEATURE, None, 8))[::-1]

    def _feabits_read(self):
        return bytes(self.cmd(opcodes.LSC_READ_FEABITS, None, 2))[::-1]

    @property
    def done(self):
        s = self.status
        return s & 0x2100 == 0x0100

@spi.Target.db.register("machxo2")
class MachXO2Spi(MachXO2Config):
    ENABLE_ARG = b'\x08\x00\x00'
    DISABLE_ARG = b'\x00\x00'
