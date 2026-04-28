"""SDM (Secure Device Manager) command/response protocol.

Transport-agnostic SDM command layer. Subclasses implement do_io()
for the specific physical transport (JTAG, FIFO, etc.).

SDM command word format (32-bit):
    [31:28]  Upper nibble (0 normally, 0xF for SYNC)
    [27:24]  ID tag (incremented per command, echoed in response)
    [23]     0
    [22:12]  Length (argument word count)
    [11]     0
    [10:0]   Command opcode

SDM response header (32-bit):
    [27:24]  ID tag (echoed from command)
    [22:12]  Length (data word count)
    [10:0]   Error code (0 = OK)
"""

import enum
import struct
from ...model import PortComponent
from ...bitfield import *

class ErrorCode(enum.IntEnum):
    OK = 0
    INVALID_COMMAND = 1
    UNKNOWN_COMMAND = 3
    INVALID_COMMAND_PARAMETERS = 4
    COMMAND_INVALID_ON_SOURCE = 6
    CLIENT_ID_NO_MATCH = 8
    INVALID_ADDRESS = 9
    AUTHENTICATION_FAIL = 0xa
    TIMEOUT = 0xb
    HW_NOT_READY = 0xc
    HW_ERROR = 0xd
    QSPI_HW_ERROR = 0x80
    QSPI_ALREADY_OPEN = 0x81
    EFUSE_SYSTEM_FAILURE = 0x82
    COMMAND_SPECIFIC_ERROR_3 = 0x83
    COMMAND_SPECIFIC_ERROR_4 = 0x84
    COMMAND_SPECIFIC_ERROR_5 = 0x85
    COMMAND_SPECIFIC_ERROR_6 = 0x86
    COMMAND_SPECIFIC_ERROR_7 = 0x87
    COMMAND_SPECIFIC_ERROR_8 = 0x88
    COMMAND_SPECIFIC_ERROR_9 = 0x89
    COMMAND_SPECIFIC_ERROR_A = 0x8A
    COMMAND_SPECIFIC_ERROR_B = 0x8B
    COMMAND_SPECIFIC_ERROR_C = 0x8C
    COMMAND_SPECIFIC_ERROR_D = 0x8D
    COMMAND_SPECIFIC_ERROR_E = 0x8E
    QSPI_OWNED_BY_SDM_IN_USER_MODE = 0x8F
    NOT_CONFIGURED = 0x100
    ALT_SDM_MBOX_RESP_DEVICE_BUSY = 0x1FF
    ALT_SDM_MBOX_RESP_NO_VALID_RESP_AVAILABLE = 0x2FF
    ALT_SDM_MBOX_RESP_ERROR = 0x3FF

class Opcode(enum.IntEnum):
    """Known SDM command opcodes for Agilex 5."""
    NOOP = 0x000
    SYNC = 0x001
    CONFIG_STATUS = 0x004
    CONFIG_REQUEST = 0x005

    GET_IDCODE = 0x010
    GET_CHIPID = 0x012
    GET_USERCODE = 0x013
    GET_VOLTAGE = 0x018
    GET_TEMPERATURE = 0x019
    GET_CONFIGURATION_TIME = 0x065

    READ_SEU_ERROR = 0x03c
    STATUS_VR = 0x713

    QSPI_OPEN = 0x032
    QSPI_CLOSE = 0x033
    QSPI_SET_CS = 0x034
    QSPI_READ_DEVICE_REG = 0x035
    QSPI_WRITE_DEVICE_REG = 0x036
    QSPI_SEND_DEVICE_OP = 0x037
    QSPI_READ_SHA = 0x06e
    QSPI_ERASE = 0x038
    QSPI_WRITE = 0x039
    QSPI_READ = 0x03A

    RSU_GET_SPT = 0x05A
    RSU_STATUS = 0x05B
    RSU_IMAGE_UPDATE = 0x5c
    RSU_NOTIFY = 0x5d

class ConfigStatus(Bitfield):
    # Word 0
    state = BooleanField(0)
    # Word 1
    fw_version = Field(32+28, 4)
    quartus_major = Field(32+16, 8)
    quartus_minor = Field(32+8, 8)
    quartus_update = Field(32, 8)
    # Word 2
    nSTATUS = BooleanField(64+31)
    nCONFIG = BooleanField(64+30)
    clk_src = MappingField(64+6, 2, [None, "Int", "Clk1", "SecurePll"])
    vid_enabled = BooleanField(64+4)
    msel = MappingField(64+0, 3, {
        0: "AvSTx32",
        1: "AS-Fast",
        3: "AS-Normal",
        5: "AvSTx16",
        6: "AvSTx8",
        7: "JTAG",
    })
    # Word 3
    hps_warmreset = BooleanField(96+5)
    hps_coldreset = BooleanField(96+4)
    seu_error = BooleanField(96+3)
    cvp_done = BooleanField(96+2)
    init_done = BooleanField(96+1)
    conf_done = BooleanField(96+0)
    # Word 4
    error_location = Field(128, 32)
    # Word 5
    error_details = Field(160, 32)

class Error(Exception):
    """SDM returned a non-zero error code."""

    def __init__(self, error_code, opcode=None):
        try:
            error_code = ErrorCode(error_code)
            ec = f"error {error_code.name}"
        except:
            error_code = int(error_code)
            ec = f"error {error_code:#x}"
        self.error_code = error_code
        self.opcode = opcode
        op = ""
        if isinstance(opcode, Opcode):
            op = f" for opcode {opcode.name}"
        elif isinstance(opcode, int):
            op = f" for opcode {opcode:#x}"
        super().__init__(f"SDM error {ec}{op}")

class FramingError(Exception):
    """SDM response framing mismatch."""


class TimeoutError(Exception):
    """No response from SDM."""


class Sdm(PortComponent):
    """Base for SDM command/response transport.

    Subclasses implement do_io() for the physical transport.
    This class provides the command serialization and response parsing.
    """

    def __init__(self, port):
        PortComponent.__init__(self, port, "sdm")
        self._id = 0

    def start(self):
        self.sync()

    def do_io(self, cmd: list[int]) -> list[int]:
        """Send a command frame and receive a response frame.

        Args:
            cmd: list of 32-bit words (header + arguments)

        Returns:
            list of 32-bit words (header + data)

        Must be implemented by transport subclass.
        """
        raise NotImplementedError

    def nop(self) -> None:
        raise NotImplementedError

    def sync(self, nonce=None):
        """Perform SDM sync handshake.

        Sends SYNC command (opcode 1) with an arbitrary nonce.
        SDM echoes the nonce back to prove it's alive.

        Returns the echoed nonce.
        """
        raise NotImplementedError

    def command(self, opcode: int, argument: bytes = b'') -> bytes:
        """Send an SDM command with arbitrary arguments.

        Args:
            opcode: SDM command opcode (11 bits)
            argument: command arguments as bytes (padded to word boundary)

        Returns:
            Response data as bytes (excluding header).

        Raises:
            Error: if SDM returns non-zero error code
            FramingError: if response length doesn't match header
            TimeoutError: if no response received
        """
        # Pack arguments as 32-bit words
        arg_words = []
        for off in range(0, len(argument), 4):
            chunk = argument[off:off + 4].ljust(4, b'\x00')
            arg_words.append(int.from_bytes(chunk, 'little'))

        cid = self._id & 0xF
        self._id += 1

        header = (opcode & 0x7FF) \
            | ((len(arg_words) & 0x7FF) << 12) \
            | ((cid & 0xF) << 24)

        rsp = self.do_io([header] + arg_words)

        if not rsp:
            raise TimeoutError(f"No response for opcode {opcode:#05x}")

        # Parse response header
        rsp_header = rsp[0]
        rsp_error = rsp_header & 0x7FF
        rsp_length = (rsp_header >> 12) & 0x7FF
        rsp_id = (rsp_header >> 24) & 0xF

        if rsp_error:
            raise Error(rsp_error, opcode=opcode)

        if len(rsp) != rsp_length + 1:
            raise FramingError(
                f"Response length mismatch: header says {rsp_length} "
                f"data words, got {len(rsp) - 1}")

        # Convert data words to bytes
        return b''.join(w.to_bytes(4, 'little') for w in rsp[1:])

    def get_idcode(self) -> int:
        """Read IDCODE via SDM."""
        data = self.command(Opcode.GET_IDCODE)
        return int.from_bytes(data[:4], 'little')

    def get_chipid(self) -> int:
        """Read 64-bit unique chip ID."""
        data = self.command(Opcode.GET_CHIPID)
        return int.from_bytes(data[:8], 'little')

    def get_usercode(self) -> int:
        """Read USERCODE."""
        data = self.command(Opcode.GET_USERCODE)
        return int.from_bytes(data[:4], 'little')

    def config_status(self) -> bytes:
        """Read configuration status (6 words = 24 bytes)."""
        v = self.command(Opcode.CONFIG_STATUS)
        v = int.from_bytes(v, "little")
        return ConfigStatus(all = v)

    def get_voltages(self, channels):
        """Retrieve voltages from core"""

        bitfield = 0
        for c in channels:
            bitfield |= 1 << int(c)

        rsp = self.command(Command.GET_VOLTAGE, int(bitfield).to_bytes(4, "little"))
        vs = [(int.from_bytes(rsp[i:i+4], "little") / 0x10000) for i in range(0, len(rsp), 4)]
        return dict(zip(sorted(channels), vs))

    def get_temperatures(self, location, channels):
        """Retrieve voltages from core"""

        bitfield = location << 16
        for c in channels:
            bitfield |= 1 << int(c)

        rsp = self.command(Command.GET_TEMPERATURE, int(bitfield).to_bytes(4, "little"))
        ret = {}
        for c, off in zip(sorted(channels), range(0, len(rsp), 4)):
            v = int.from_bytes(rsp[off:off+4], "little")
            if v & 0x80000000:
                ret[(location, c)] = None
            else:
                ret[(location, c)] = ((v & ~0xf0000000) - (v & 0x10000000)) / 0x100
        return ret

    def qspi_open(self):
        """Enable QSPI flash access."""
        self.command(Opcode.QSPI_OPEN)

    def qspi_close(self):
        """Disable QSPI flash access."""
        self.command(Opcode.QSPI_CLOSE)

    def qspi_set_cs(self, cs: int):
        """Select QSPI chip select line (0-3)."""
        self.command(
            Opcode.QSPI_SET_CS,
            int(cs << 28).to_bytes(4, 'little'))

    def qspi_read(self, address: int, word_count: int) -> bytes:
        """Read from QSPI flash. Address must be word-aligned."""
        arg = struct.pack('<II', address, word_count)
        return self.command(Opcode.QSPI_READ, arg)

    def qspi_write(self, address: int, data: bytes):
        """Write to QSPI flash. Address must be word-aligned."""
        word_count = (len(data) + 3) // 4
        arg = struct.pack('<II', address, word_count) + data
        self.command(Opcode.QSPI_WRITE, arg)

    def qspi_erase(self, address: int, word_count: int):
        """Erase QSPI flash region. Address must be word-aligned."""
        arg = struct.pack('<II', address, word_count)
        self.command(Opcode.QSPI_ERASE, arg)

    def qspi_read_device_reg(self, opcode: int, byte_count: int) -> bytes:
        """Read a QSPI device register (e.g. JEDEC ID)."""
        arg = struct.pack('<II', opcode, byte_count)
        return self.command(
            Opcode.QSPI_READ_DEVICE_REG, arg)

    def config_request(self) -> bytes:
        """Read a QSPI device register (e.g. JEDEC ID)."""
        return self.command(Opcode.CONFIG_REQUEST)
