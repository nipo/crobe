from ..model import JtagSramFpga
from ...model import PortComponent
from ...part_id import PartId
from ...protocol import jtag, spi, i2c
from ... import bitfield
from ...util.endian import bitswap8
from ... import bitstring
from . import bitstream, parts
import time

class MachXO2Config(jtag.InstructionRegistry):
    ERASE_SRAM = 1
    ERASE_FEATURE = 2
    ERASE_FLASH = 4
    ERASE_UFM = 8

    class Status(bitfield.Bitfield):
        TransparentMode = bitfield.BooleanField(0)
        Target          = bitfield.MappingField(1, 3, {0: "SRAM", 1: "EFUSE", 2: "Feature", 4:"Flash"}),
        JTAG            = bitfield.BooleanField(4)
        LogicPwProt     = bitfield.BooleanField(5)
        SRAM_OTP        = bitfield.BooleanField(6)
        Decrypt         = bitfield.BooleanField(7)
        Done            = bitfield.BooleanField(8)
        ISC             = bitfield.BooleanField(9)
        Write           = bitfield.BooleanField(10)
        Read            = bitfield.BooleanField(11)
        Busy            = bitfield.BooleanField(12)
        Fail            = bitfield.BooleanField(13)
        FeatureOTP      = bitfield.BooleanField(14)
        DecryptOnly     = bitfield.BooleanField(15)
        PasswProt       = bitfield.BooleanField(16)
        UFM_OTP         = bitfield.BooleanField(17)
        Assp            = bitfield.BooleanField(18)
        Sdmen           = bitfield.BooleanField(19)
        EncPreamble     = bitfield.BinaryField(20, "none", "detected")
        StdPream        = bitfield.BinaryField(21, "none", "detected")
        SPI             = bitfield.BinaryField(22, "OK", "Fail")
        Error           = bitfield.MappingField(23, 3, ["OK", "ID", "Bad command", "CRC", "Preamble", "Abort", "Overflow", "SRAM ovr."]),
        ExecutionError  = bitfield.BooleanField(26)
        IDMismatch      = bitfield.BooleanField(27)
        InvalidCommand  = bitfield.BooleanField(28)
        SEDError        = bitfield.BooleanField(29)
        Bypass          = bitfield.BooleanField(30)
        FlowThroughMode = bitfield.BooleanField(31)

    class Ctrl0(bitfield.Bitfield):
        MasterClockFreq         = bitfield.Field(0, 6)
        SPIMode                 = bitfield.Field(6, 2)
        SPILsbFirst             = bitfield.BooleanField(8)
        MCLKB                   = bitfield.Field(9, 1)
        STX_DUM                 = bitfield.Field(10, 2)
        DONE                    = bitfield.Field(12, 3)
        INIT                    = bitfield.Field(15, 3)
        P_DONE                  = bitfield.Field(18, 2)
        SPIMaster               = bitfield.BooleanField(20)
        SPISlaveSlowRespondMode = bitfield.BooleanField(21)
        CPUMon                  = bitfield.BooleanField(22)
        SSPIAuto                = bitfield.BooleanField(23)
        HFC                     = bitfield.BooleanField(24)
        TranEdit                = bitfield.BooleanField(25)
        CDM                     = bitfield.BooleanField(26, inverted = True)
        BKE                     = bitfield.BooleanField(27, inverted = True)
        NDR                     = bitfield.BooleanField(28)
        WakeUp                  = bitfield.BooleanField(29)
        CoreClockSel            = bitfield.Field(30, 2)

    class Feature(bitfield.Bitfield):
        IDCODE   = bitfield.Field(0, 32)
        TRACEID  = bitfield.Field(32, 8)
        I2CAddr  = bitfield.Field(40, 8)
        Secpwd   = bitfield.BooleanField(48)
        Deconly  = bitfield.BooleanField(49)
        Pwdflash = bitfield.BooleanField(50)
        Pwdall   = bitfield.BooleanField(51)
        Myassp   = bitfield.BooleanField(52)
        Program  = bitfield.BooleanField(53)
        Init     = bitfield.BooleanField(54)
        Done     = bitfield.BooleanField(55)
        Jtag     = bitfield.BooleanField(56)
        Sspi     = bitfield.BooleanField(57)
        I2c      = bitfield.BooleanField(58)
        Mspi     = bitfield.BooleanField(59)
        Boots1   = bitfield.BooleanField(60)
        Boots2   = bitfield.BooleanField(61)
        Rsvd     = bitfield.Field(62, 2)

    class TraceId(bitfield.Bitfield):
        User  = bitfield.Field(56, 8)
        Lot   = bitfield.Field(24, 32)
        Wafer = bitfield.Field(19, 5)
        X     = bitfield.Field(12, 7)
        Y     = bitfield.Field(5, 7)
        Spare = bitfield.Field(0, 5)

    ISC_ADDRESS   = jtag.Dr(None)
    ISC_SECTOR    = jtag.Dr(8)
    ISC_DEFAULT   = jtag.Dr(1)
    BUSY          = jtag.Dr(1)
    ISC_DATA      = jtag.Dr(None)
    ISC_CONFIG    = jtag.Dr(8)
    ISC_PDATA     = jtag.Dr(None)
    NV_DATA       = jtag.Dr(128)
    BOUNDARY      = jtag.Dr(208)
    MANUFACTURING = jtag.Dr(128)
    PASSWORD      = jtag.Dr(64)
    STATUS        = jtag.Dr(32)
    CTRL0         = jtag.Dr(32)
    FEATURE       = jtag.Dr(64)
    FEABITS       = jtag.Dr(16)
    BITSTREAM     = jtag.Dr(None)
    DR_UNKNOWN    = jtag.Dr(None)
    PAGE_ADDRESS  = jtag.Dr(32)

    ER1           = jtag.Instruction(0x32, None)
    ER2           = jtag.Instruction(0x38, None)
    
    CLAMP                = jtag.Instruction(0x78, "TAP_BYPASS")
    EXTEST               = jtag.Instruction(0x15, "BOUNDARY")
    HIGHZ                = jtag.Instruction(0x18, "TAP_BYPASS")
    IDCODE               = jtag.Instruction(0xe0, "DEVICE_ID")
    IDCODE_PRIV          = jtag.Instruction(0x16, "DEVICE_ID")
    ISC_ADDRESS_SHIFT    = jtag.Instruction(0x42, "ISC_ADDRESS")
    ISC_DATA_SHIFT       = jtag.Instruction(0x0a, "ISC_DATA")
    ISC_DISABLE          = jtag.Instruction(0x26, "ISC_DEFAULT")
    ISC_DISCHARGE        = jtag.Instruction(0x14, "ISC_DEFAULT")
    ISC_ENABLE           = jtag.Instruction(0xc6, "ISC_CONFIG")
    ISC_ERASE            = jtag.Instruction(0x0e, "ISC_SECTOR")
    ISC_ERASE_DONE       = jtag.Instruction(0x24, "ISC_DEFAULT")
    ISC_NOOP             = jtag.Instruction(0x30, "ISC_DEFAULT")
    ISC_PROGRAM          = jtag.Instruction(0x67, "ISC_PDATA")
    ISC_PROGRAM_DONE     = jtag.Instruction(0x5e, "ISC_DEFAULT")
    ISC_PROGRAM_SECURITY = jtag.Instruction(0xce, "ISC_DEFAULT")
    ISC_PROGRAM_USERCODE = jtag.Instruction(0xc2, "DEVICE_ID")
    ISC_READ             = jtag.Instruction(0x80, "ISC_PDATA")
    LSC_ENABLE_X         = jtag.Instruction(0x74, "ISC_CONFIG")
    LSC_PROGRAM_SECPLUS  = jtag.Instruction(0xcf, "ISC_DEFAULT")
    PRELOAD              = jtag.Instruction(0x1c, "BOUNDARY")
    SAMPLE               = jtag.Instruction(0x1c, "BOUNDARY")
    USERCODE             = jtag.Instruction(0xc0, "DEVICE_ID")

    LSC_RESET_CRC        = jtag.Instruction(0x3b, "DR_UNKNOWN")
    LSC_PROG_SED_CRC     = jtag.Instruction(0xa2, "DR_UNKNOWN")
    LSC_WRITE_BUS_ADDRESS= jtag.Instruction(0xf6, "DR_UNKNOWN")
    LSC_EBR_WRITE        = jtag.Instruction(0xb2, "DR_UNKNOWN")
    LSC_PCS_WRITE        = jtag.Instruction(0x72, "DR_UNKNOWN")
    LSC_WRITE_ADDRESS    = jtag.Instruction(0xb4, "PAGE_ADDRESS")
    VERIFY_ID            = jtag.Instruction(0xe2, "DR_UNKNOWN")
    LSC_WRITE_COMP_DIC   = jtag.Instruction(0x02, "DR_UNKNOWN")
    LSC_INIT_ADDRESS     = jtag.Instruction(0x46, None)
    LSC_INIT_ADDRESS_UFM = jtag.Instruction(0x47, None)
    LSC_PROG_INCR_RTI    = jtag.Instruction(0x82, "DR_UNKNOWN")
    LSC_VERIFY_INCR_RTI  = jtag.Instruction(0x6a, "DR_UNKNOWN")

    LSC_PROG_INCR_CMP    = jtag.Instruction(0xb8, "NV_DATA")
    LSC_PROG_INCR_NV     = jtag.Instruction(0x70, "NV_DATA")

    LSC_PROG_CTRL0       = jtag.Instruction(0x22, "CTRL0")
    LSC_READ_CTRL0       = jtag.Instruction(0x20, "CTRL0")
    LSC_PROG_FEATURE     = jtag.Instruction(0xe4, "FEATURE")
    LSC_READ_FEATURE     = jtag.Instruction(0xe7, "FEATURE")
    LSC_PROG_FEABITS     = jtag.Instruction(0xf8, "FEABITS")
    LSC_READ_FEABITS     = jtag.Instruction(0xfb, "FEABITS")
    LSC_READ_PASSWORD    = jtag.Instruction(0xf2, "PASSWORD")
    LSC_READ_STATUS      = jtag.Instruction(0x3c, "STATUS")

    LSC_READ_INCR_NV     = jtag.Instruction(0x73, "NV_DATA")
    LSC_CHECK_BUSY       = jtag.Instruction(0xf0, "BUSY")
    LSC_REFRESH          = jtag.Instruction(0x79, "ISC_DEFAULT")
    LSC_BITSTREAM_BURST  = jtag.Instruction(0x7a, "BITSTREAM")
    LSC_UIDCODE_PUB      = jtag.Instruction(0x19, "DEVICE_ID")
    LSC_MANUFACTURING    = jtag.Instruction(0x90, "MANUFACTURING")
    LSC_SHIFT_PASSWORD   = jtag.Instruction(0xbc, "PASSWORD")
    
    def __init__(self):
        jtag.InstructionRegistry.__init__(self)
        self.__bg_enable = None

    @classmethod
    def chip_info(cls, idcode):
        possible_parts = [p for p in parts.PARTS if int(idcode) == p.idcode]
        if not possible_parts:
            return None

        if len(possible_parts) > 1:
            suffixes = [p.name.split("-", 1)[1] for p in possible_parts]
            prefix = possible_parts[0].name.split("-", 1)[0]
            name = prefix + "-" + "/".join(suffixes)
            info = possible_parts[0]
        else:
            info = possible_parts[0]
            name = info.name
        return name, info

    def start(self):
        ni = self.chip_info(self.idcode)
        if not ni:
            self._isc_enable(self.TARGET_FLASH, True)
            idcode = self.IDCODE_PRIV.shift(0)
            ni = self.chip_info(idcode)
            self.logger.info("IDCode priv: 0x%x", idcode)

        assert ni

        self.name, self.info = ni

        self.ISC_DATA.length = self.info.col_bit_count
        self.ISC_PDATA.length = self.info.col_bit_count
        self.ISC_ADDRESS.length = self.info.row_count
            
        self.config_memory_size = self.info.row_count * self.info.col_bit_count // 8
        self.flash_size = (self.info.flash_page_count + self.info.ufm_page_count) * 16

        self.logger.trace("Found %s", self.info.name)

        self.uid = self.LSC_UIDCODE_PUB.shift(0)

        self.logger.info(repr(self.TraceId(self.uid)))
        self.logger.info(repr(self.Status(self.status_get())))

        try:
            self._isc_enable(True)
            self.logger.info(repr(self.Feature(self.feature_get())))
            self._isc_disable()
        except RuntimeError:
            self.logger.warning("Unable to background enable")

    TARGET_SRAM    = 0
    TARGET_EFUSE   = 2
    TARGET_FEATURE = 4
    TARGET_FLASH   = 8
        
    def _isc_enable(self, target = TARGET_FLASH, background = None):
        if background is None:
            background = self.__bg_enable

        cmd = self.LSC_ENABLE_X if background else self.ISC_ENABLE
        self.execute([cmd.cmd(target), self.cmd_run(1)])

        self.wait_no_fail()
        self.status_check(0, 0x0200)
        self.__bg_enable = background

    def _isc_disable(self):
        if self.__bg_enable is None:
            return
        self.execute([self.ISC_DISABLE.cmd(), self.cmd_run(1)])
        self.__bg_enable = None

    def done_get(self):
        return self.ir_status_read() & 0x84 == 0x04

    def _erase(self, what):
        assert self.__bg_enable is not None
        bg = self.__bg_enable
        self.execute([self.ISC_ERASE.cmd(what), self.cmd_run(100)])
        self.wait_idle(20)
        self._isc_enable(self.TARGET_FLASH, background = bg)

    def _stop(self):
        self._erase(self.ERASE_SRAM)

    def stop(self):
        self._isc_enable(self.TARGET_FLASH, False)
        self._stop()
        self._isc_disable()

    def reset(self):
        self.refresh()
        
    def refresh(self):
        self._refresh()

    def _refresh(self):
        self.execute([
            self.ISC_DISABLE.cmd(0),
            self.cmd_run(1000),
            self.LSC_REFRESH.cmd(0),
            self.cmd_run(1000),
            ])
        time.sleep(.01)
        self.__bg_enable = False
        
    def _erase_all(self):
        self._erase(self.ERASE_SRAM | self.ERASE_UFM | self.ERASE_FLASH | self.ERASE_FEATURE)

    def erase_all(self):
        self._isc_enable(self.TARGET_FLASH, False)
        self._erase_all()
        self._isc_disable()

    def status_get(self):
        return self.LSC_READ_STATUS.shift(0)

    def feature_get(self):
        return self.LSC_READ_FEATURE.shift(0)

    def busy_get(self):
#        return self.Status(self.status_get()).Busy
        return self.LSC_CHECK_BUSY.shift(0) & 1

    def status_check(self, expect_clear, expect_set):
        mask = expect_set | expect_clear
        status = self.status_get()
        if status & mask == expect_set:
            return
        self.logger.warning(repr(self.Status(status)))
        raise ValueError("Expected status with 0x%08x set, 0x%08x clear, got 0x%08x" %
                         (expect_set, expect_clear, status))

    def wait_idle(self, timeout = 1.):
        step = .01

        for i in range(max(int(timeout / step), 1)):
            self.run(1)
            b = self.busy_get()
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
        return self._mem_read(offset, size, self.LSC_INIT_ADDRESS, 0)

    def _ufm_read(self, offset, size):
        return self._mem_read(offset, size, self.LSC_INIT_ADDRESS_UFM, 0x40000000)

    def _mem_read(self, offset, size, addr_init_op, offset_base):
        assert self.__bg_enable is not None
        self._isc_enable(self.TARGET_FLASH, True)
        self.status_check(0, 0xa00)

        addr_init_op.shift(offset_base >> 28)
        self.wait_no_fail()

        self.execute([
            self.LSC_WRITE_ADDRESS.cmd(offset_base + offset // 16),
            self.cmd_run(1),
            ])
        self.wait_no_fail()

        data = b''
        for addr in range(offset & ~0xf, offset + size, 16):
            cmds = [
                self.LSC_READ_INCR_NV.cmd(None),
                self.cmd_run(10),
                self.cmd_dr_shift(None, None,
                                16 * 8,
                                read_tdo = True,
                                return_type = bytes),
                ]
            self.execute(cmds)

            data += cmds[2].tdo

        data = self.row_flip(data)

        return data[offset & 0xf : (offset & 0xf) + size]

    def _mem_write(self, offset, data, addr_init_op, offset_base):
        self.status_check(0, 0x600)

        if offset % 16:
            prelen = (-offset % 16)
            self.logger.debug("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            offset = offset & ~0xf

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.debug("Post len %d", postlen)
            data += b'\x00' * postlen

        self.execute([
            addr_init_op.cmd(0),
            self.cmd_run(1),
            ])
        self.wait_no_fail()

        if offset:
            self.LSC_WRITE_ADDRESS(offset_base + offset // 16)
            self.run(1)
            self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            w = self.LSC_PROG_INCR_NV.cmd(bytes(data[off : off+16]))
            cmds = [
                w,
                self.cmd_run(1000),
                ]

            self.execute(cmds)
            self.wait_no_fail()

    def _flash_write(self, offset, data):
        return self._mem_write(offset, data, self.LSC_INIT_ADDRESS, 0x20000000)

    def _ufm_write(self, offset, data):
        return self._mem_write(offset, data, self.LSC_INIT_ADDRESS_UFM, 0x40000000)

    def _flash_done_set(self):
        self.execute([
            self.ISC_PROGRAM_DONE.cmd(),
            self.cmd_run(20000),
            ])

    def flash_erase(self):
        self._isc_enable(self.TARGET_FLASH, True)
        self._flash_erase()
        self._isc_disable()

    def ufm_erase(self):
        self._isc_enable(self.TARGET_FLASH, True)
        self._ufm_erase()
        self._isc_disable()

    def flash_read(self, offset, size):
        self._isc_enable(self.TARGET_FLASH, False)
        ret = self._flash_read(offset, size)
        self._isc_disable()
        return ret

    def ufm_read(self, offset, size):
        self._isc_enable(self.TARGET_FLASH, False)
        ret = self._ufm_read(offset, size)
        self._isc_disable()
        return ret

    def flash_write(self, offset, data):
        self._isc_enable(self.TARGET_FLASH, False)
        self._flash_write(offset, data)
        self._isc_disable()

    def ufm_write(self, offset, data):
        self._isc_enable(self.TARGET_FLASH, True)
        self._ufm_write(offset, data)
        self._isc_disable()

    def feature_read(self):
        self._isc_enable(self.TARGET_FLASH, True)
        ret = self._feature_read()
        self._isc_disable()
        return ret

    def feabits_read(self):
        self._isc_enable(self.TARGET_FLASH, True)
        ret = self._feabits_read()
        self._isc_disable()
        return ret

    def _feature_read(self):
        return self.LSC_READ_FEATURE.shift(0, return_type = bytes)

    def _feabits_read(self):
        return self.LSC_READ_FEABITS.shift(0, return_type = bytes)

    def _feature_write(self, feature):
        self._isc_enable(self.TARGET_FLASH, True)
        self.execute([
            self.LSC_INIT_ADDRESS.cmd(0x02),
            self.cmd_run(1000),
            self.LSC_PROG_FEATURE.cmd(bitstring.BitString(feature)),
            self.cmd_run(1000),
            ])

    def _feabits_write(self, feabits):
        self.execute([
            self.LSC_PROG_FEABITS.cmd(bitstring.BitString(feabits)),
            self.cmd_run(1000),
            ])

@jtag.Chain.db.register(*set([PartId.from_idcode(p.idcode).drop_revision() for p in parts.PARTS]))
class MachXO2(jtag.Tap, MachXO2Config, JtagSramFpga):
    """JTAG-based specialization of Mach-XO2 controller

    In addition to non-volatile commands, this also supports loading a
    bitstream directly into SRAM.
    """
    irlen = 8
    max_freq = 25e6

    USER_IR = [0x32, 0x38]

    def __init__(self, port, index, idcode):
        jtag.Tap.__init__(self, port, index, idcode)
        MachXO2Config.__init__(self)
        JtagSramFpga.__init__(self, self.name)

    def start(self):
        MachXO2Config.start(self)

    def load(self, config):
        from ...loadable.object import Program

        assert isinstance(config, Program)
        #bs = bitstream.Bitstream(parts.PARTS, config)
        #self.ram_load(bs)

        data = config.segment_at(0).data
        if data.startswith(bitstream.Bitstream.HEADER):
            data = bitswap8(data)
        self.ram_load2(data)

    def ram_load(self, bs):
        assert self.idcode.is_same_part(PartId.from_idcode(bs.info.idcode))
        self._isc_enable(self.TARGET_FLASH, False)
        self._erase(self.ERASE_SRAM)

        bs_cmds = [
            self.LSC_PROG_CTRL0.cmd(0x40000000),
            self.cmd_run(10),
            self.LSC_INIT_ADDRESS.cmd(0),
            self.cmd_run(10),
        ]

        for frame in bs.rti:
            data = frame.data
            data = bitswap8(data)
            bs_cmds.extend([
                self.LSC_PROG_INCR_RTI.cmd(bytes(data)),
                self.cmd_run(10),
            ])

        bs_cmds.extend([
            self.USERCODE.cmd(0),
            self.ISC_PROGRAM_USERCODE.cmd(),
            self.cmd_run(100),
            self.ISC_PROGRAM_DONE.cmd(),
            self.cmd_run(100),
            self.BYPASS.cmd(),
        ])

        self.execute(bs_cmds)

        self._isc_disable()
        
        self.BYPASS.shift()
        self.run(1)

    def ram_load2(self, bs):
        self._isc_enable(self.TARGET_SRAM, False)

        bs_cmds = [
            self.LSC_INIT_ADDRESS.cmd(1),
            self.cmd_run(10),
            self.LSC_BITSTREAM_BURST.cmd(b'\xff' * 48 + bytes(bs)),
            self.cmd_run(10),
        ]
        self.execute(bs_cmds)

        self._isc_disable()
        self.BYPASS.shift()
        self.run(1)

    @staticmethod
    def row_flip(data):
        assert len(data) % 16 == 0
        tmp = b""
        for offset in range(0, len(data), 16):
            tmp += bitswap8(data[offset : offset + 16])
        return tmp

class SerIrMap:
    """Holds the definition betzeen a given JTAG commands and I2C/SPI
    transport.

    JTAG transport is simple: Instruction selects relevant DR.
    For I2C/SPI, lattice has some kind of crazy wrapper where general
    format is:
    [Instruction (1 byte)] [Operand (1 to 3 bytes)] [Data (in or out, optional)]

    - instruction is written first,
    - depending on the instruction, operand is the data usually shifted to DR,
    - if no operand and/or no data, there is still a need for some padding,
    - data phase, if any, comes after operand and padding.

    Then there are strange padding rules for non-byte-aligned DRs, but
    the only actual example is busy bit, then we'll have a special
    case for it.
    """

    def __init__(self,
                 data_direction = None, operand_size = 0,
                 operand = 0, align_count = 3, post_wait = 0):
        """
        data_direction: either
        - None if tdi/tdo is usually not used for this instruction,
        - "op" if data usually shifted to TDI should be mapped to perands,
        - "read" if data is usually shifted out of device through TDO,
        - "write" if data is usually shifted to device.

        operand_size: operand field byte count. Operand value will be
        mapped big-endian to it.

        operand: Constant value ORed to operand data field (if any, i.e.
        in "op" mode). Allows to inject a constant operand value for
        some commands.

        align_count: expected size of operand before data phase or end
        of transaction.

        post_wait: time to wait after completion of command.
        """
        self.operand_size = operand_size
        self.operand = operand
        self.align_count = align_count if align_count is not None else operand_size
        self.data_direction = data_direction
        self.post_wait = post_wait

    def op_run(self, mach, op):
        assert op.tdi is None or isinstance(op.tdi, bitstring.BitString)
        operand = self.operand
        if self.data_direction == "op":
            if op.tdi is not None:
                if len(op.tdi) > self.operand_size * 8:
                    raise RuntimeError("TDI too big: %s, %d operand bytes" % (op.tdi, self.operand_size))
                operand |= int(op.tdi)

        out_data = bytes([op.ir & 0xff]) + operand.to_bytes(self.operand_size, "big").ljust(self.align_count, b"\x00")

        if self.data_direction == "read":
            io_len = len(op.tdi)
            assert io_len == 1 or (io_len % 8 == 0)

            in_data_byte_count = (io_len + 7) // 8

            mach.logger.info("i2c < %s, %d", out_data.hex(), in_data_byte_count)
            
            r = mach.do_write_read(out_data, in_data_byte_count)

            mach.logger.info("i2c > %s", r.hex())

            if io_len == 1:
                tdo = bitstring.BitString(r[0] >> 7, 1)
            else:
                tdo = bitstring.BitString(r[::-1])

            op.tdo = op.postprocess(tdo)
            return
            
        if self.data_direction == "write":
            out_data += bytes(op.tdi)[::-1]
        
        mach.logger.info("i2c < %s", out_data.hex())
        mach.do_write(out_data)

        if self.post_wait:
            time.sleep(self.post_wait)

class MachXO2Serial(PortComponent, MachXO2Config):
    """
    Utility class that wraps the JTAG commands to serial (I2C/SPI) transport.
    """

    def __init__(self, bus, **kwargs):
        PortComponent.__init__(self, bus, "MachXO2", **kwargs)
        MachXO2Config.__init__(self)

    def start(self):
        PortComponent.start(self)
        MachXO2Config.start(self)

    def busy_get(self):
        return not not (self.LSC_READ_STATUS.shift(0) & 0x1000)

    _reg_map = {
        0xe0: SerIrMap("read"),
        0x16: SerIrMap("read"),
        0x74: SerIrMap("op", operand_size = 1, align_count = 2, post_wait = .1),
        0xc6: SerIrMap("op", operand_size = 1, align_count = 2, post_wait = .1),
        0xf0: SerIrMap("read"),
        0x3c: SerIrMap("read"),
        0x0e: SerIrMap("op", operand_size = 1),
        0xcb: SerIrMap(),
        0x46: SerIrMap(),
        0xb4: SerIrMap("write"),
        0x70: SerIrMap("write", operand_size = 3, operand = 1),
        0x47: SerIrMap(),
        0xc9: SerIrMap("write", operand_size = 3, operand = 1),
        0xc2: SerIrMap("write"),
        0xc0: SerIrMap("read"),
        0xe4: SerIrMap("write"),
        0xe7: SerIrMap("read"),
        0xf8: SerIrMap("write"),
        0xfb: SerIrMap("read"),
        0x73: SerIrMap("read", operand_size = 3),
        0xca: SerIrMap("read", operand_size = 3),
        0x5e: SerIrMap(),
        0xf9: SerIrMap("write"),
        0xfa: SerIrMap("read"),
        0xff: SerIrMap(operand = 0xffffff, operand_size = 3),
        0x26: SerIrMap(align_count = 2, post_wait = .3),
        0x79: SerIrMap(align_count = 2, post_wait = .3),
        0xce: SerIrMap(),
        0xcf: SerIrMap(),
        0x19: SerIrMap("read"),
    }

    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
        else:
            return PortComponent.option_set(opt)

    def run(self, cycles = 1):
#        self.BYPASS.shift()
        time.sleep(cycles / 1e5)

    def cmd_dr_shift(self, ir, dr, length = None, read_tdo = True, read_ir = False, return_type = None):
        return jtag.TapDrShift(ir, dr, length, read_tdo, read_ir, return_type)

    def cmd_run(self, cycles):
        return jtag.TapRun(cycles)
    
    def _flash_done_set(self):
        pass

    def _refresh(self):
        self.execute([
            self.ISC_ERASE.cmd(self.ERASE_SRAM),
            self.LSC_REFRESH.cmd(0),
            ])
        time.sleep(.1)

    def _mem_read(self, offset, size, addr_init_op, offset_base):
        self.status_check(0, 0xa00)

        addr_init_op.shift(offset_base >> 28)
        self.wait_no_fail()

        self.execute([
            self.LSC_WRITE_ADDRESS.cmd(offset_base + offset // 16),
            self.cmd_run(1),
            ])
        self.wait_no_fail()

        data = b''
        for addr in range(offset & ~0xf, offset + size, 16):
            cmds = [
                self.LSC_READ_INCR_NV.cmd(0,
                                          read_tdo = True,
                                          return_type = bytes),
                ]
            self.execute(cmds)

            data += cmds[0].tdo

        data = self.row_flip(data)

        return data[offset & 0xf : (offset & 0xf) + size]

    @staticmethod
    def row_flip(data):
        assert len(data) % 16 == 0
        tmp = b""
        for offset in range(0, len(data), 16):
            tmp += data[offset : offset + 16][::-1]
        return tmp

    def do_write_read(self, wdata, rdata_len):
        """
        Must be implemented in transport
        """
        ...

    def do_write(self, wdata):
        """
        Must be implemented in transport
        """
        ...

@i2c.Interface.db.register("machxo2")
class MachXO2I2c(i2c.Slave, MachXO2Serial):
    """
    I2C-based specialization of Mach-XO2 controller
    """

    def __init__(self, port):
        i2c.Slave.__init__(self, port, "Mach-XO2", saddr = None)
        MachXO2Serial.__init__(self, port)

    def start(self):
        assert self.saddr is not None
        i2c.Slave.start(self)
        MachXO2Serial.start(self)
        
    def execute(self, ops):
        for op in ops:
            if isinstance(op, jtag.TapDrShift):
                ir = op.ir & 0xff
                mapper = self._reg_map[ir]
                for retry in range(10, -1, -1):
                    try:
                        mapper.op_run(self, op)
                        break
                    except i2c.AddressNack:
                        if not retry:
                            raise
                        self.logger.debug("nack")
                    time.sleep(.01)
            elif isinstance(op, jtag.TapRun):
                time.sleep(.001)
            else:
                raise RuntimeError("No mapping for %s"%op)

    def do_write_read(self, wdata, rdata_len):
        return i2c.Slave.write_read(self, wdata, rdata_len)

    def do_write(self, wdata):
        return i2c.Slave.write(self, wdata)
            
@spi.Target.db.register("machxo2")
class MachXO2Spi(MachXO2Serial):
    """
    SPI-based specialization of Mach-XO2 controller
    """

    def __init__(self, port, name, cs):
        super().__init__(port, cs = cs)

    def execute(self, ops):
        for op in ops:
            if isinstance(op, jtag.TapDrShift):
                mapper = self._reg_map[op.ir & 0xff]
                mapper.op_run(self, op)
            elif isinstance(op, jtag.TapRun):
                time.sleep(.001)
            else:
                raise RuntimeError("No mapping for %s"%op)

    def do_write_read(self, wdata, rdata_len):
        r = self.cmd_shift(rdata_len, read_miso = True)
        self.port.execute([self.cmd_cs(True),
                           self.cmd_shift(wdata),
                           r,
                           self.cmd_cs(False)])
        return r.miso

    def do_write(self, wdata):
        return self.transaction(wdata, read_miso = False)
