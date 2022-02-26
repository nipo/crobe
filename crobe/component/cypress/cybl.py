from ...protocol import i2c
import time
import enum
import math
from ...util.crc import crc

__all__ = ["CyBl"]

@i2c.Interface.db.register("cybl")
class CyBl(i2c.Slave):
    def __init__(self, port, saddr = None):
        i2c.Slave.__init__(self, port, "CyBl", saddr)
        self.checksum_mode = "sum"
        self.row_size = 128
        self.command_buffer_size = 32

    @property
    def chunk_size(self):
        return 2 ** int(math.log2(self.command_buffer_size - 7))
        
    def checksum(self, blob):
        if self.checksum_mode == "crc":
            return crc(blob, 0, 0x11021, pop_lsb = False, push_lsb = True, inv_state = False)
        elif self.checksum_mode == "sum":
            return (-sum(blob, 0)) & 0xffff
        else:
            raise NotImplementedError(self.checksum_mode)
        
    def row_checksum(self, blob):
        return (-sum(blob, 0)) & 0xff
        
    def option_set(self, opt):
        if opt.startswith("checksum_mode="):
            val = opt[14:]
            assert val in ["crc", "sum"]
            self.checksum_mode = val
            return

        i2c.Slave.option_set(self, opt)

    def start(self):
        self.enter_bootloader()

        i2c.Slave.start(self)

    class Cmd(enum.IntEnum):
        VERIFY_CHECKSUM        = 0x31
        GET_FLASH_SIZE         = 0x32
        GET_APPLICATION_STATUS = 0x33
        ERASE_ROW              = 0x34
        SYNC_BOOTLOADER        = 0x35
        SET_ACTIVE_APP         = 0x36
        SEND_DATA              = 0x37
        ENTER_BOOTLOADER       = 0x38
        PROGRAM_ROW            = 0x39
        VERIFY_ROW             = 0x3a
        EXIT_BOOTLOADER        = 0x3b

    class Error(enum.IntEnum):
        SUCCESS  = 0x00
        VERIFY   = 0x02
        LENGTH   = 0x03
        DATA     = 0x04
        CMD      = 0x05
        DEVICE   = 0x06
        VERSION  = 0x07
        CHECKSUM = 0x08
        ARRAY    = 0x09
        ROW      = 0x0A
        APP      = 0x0C
        ACTIVE   = 0x0D
        UNK      = 0x0F

    FRAME_START         = 0x01
    FRAME_END           = 0x17

    def frame_send(self, command, data = b''):
        blob = bytes([self.FRAME_START, command, len(data) & 0xff, len(data) >> 8]) + data
        chk = self.checksum(blob)
        blob += bytes([chk & 0xff, chk >> 8, self.FRAME_END])

        self.logger.protocol("frame send %s", blob.hex())

        self.write(blob)

    def frame_receive(self, expected_size = None):
        data = b''
        if expected_size is None:
            expected_size = 32

        for retry in range(10):
            try:
                data += self.read(expected_size + 7)
            except i2c.AddressNack:
                time.sleep(.02)
                continue

            st = data.find(bytes([self.FRAME_START]))
            if st < 0:
                data = b''
                time.sleep(.02)
                continue

            data = data[st:]
            
            self.logger.protocol("frame recv %s", data.hex())

            length = int.from_bytes(data[2:4], "little")
            chk_ext = int.from_bytes(data[length+4:length+6], "little")
            chk = self.checksum(data[:length + 4])

            if chk != chk_ext:
                raise ValueError("Bad checksum", hex(chk_ext), hex(chk))

            if data[length + 6] != self.FRAME_END:
                raise ValueError("Bad end tag")

            return data[1], data[4 : length + 4]

        raise ValueError("Not a frame", data.hex())

    def transact(self, command, data = b'', expected_size = None):
        for retry in range(3):
            self.frame_send(command, data)
            time.sleep(.03)
            try:
                rsp, data = self.frame_receive(expected_size)
                rsp = self.Error(rsp)
            except ValueError:
                continue
            if rsp != self.Error.SUCCESS:
                raise RuntimeError(rsp)
            return data
        raise RuntimeError("No answer")

    def verify_checksum(self):
        """
        Returns whether app checksum is valid.
        """
        data = self.transact(self.Cmd.VERIFY_CHECKSUM, expected_size = 1)

        # If 0, checksum is bad.
        return data[0] != 0

    def get_flash_size(self, *, array_id):
        """
        Retrieves characteristics of flash bank.
        Returns:
        - First row of the bootloadable flash,
        - Last row of the bootloadable flash.
        """
        data = self.transact(self.Cmd.GET_FLASH_SIZE, bytes([array_id]), expected_size = 4)
        first_row = int.from_bytes(data[:2], "little")
        last_row = int.from_bytes(data[2:4], "little")

        return first_row, last_row

    def get_application_status(self, *, app_number):
        """
        Checks whether the specified application is valid and if it is active.
        Returns:
        - Valid application number,
        - Active application number.
        """
        data = self.transact(self.Cmd.GET_APPLICATION_STATUS, bytes([app_number]), expected_size = 2)

        return data[0], data[1]

    def erase_row(self, *, array_id, row_number):
        """
        Erases contents of the selected flash row.
        """
        data = self.transact(self.Cmd.ERASE_ROW, bytes([array_id, row_number & 0xff, row_number >> 8]), expected_size = 0)

    def sync_bootloader(self):
        """
        Resets the bootloader to a clean state. Any data that was buffered
        in will be thrown out. This command is needed only if the
        bootloader and the host become out of sync with each other.
        """
        data = self.transact(self.Cmd.SYNC_BOOTLOADER, expected_size = 0)

    def set_active_application(self, *, app_number):
        """
        Sets the specified application as active.
        """
        data = self.transact(self.Cmd.SET_ACTIVE_APP, bytes([app_number]), expected_size = 0)

    def send_data(self, data):
        """
        The received data bytes will be buffered by the bootloader in
        anticipation of the Program Row command.
        """
        data = self.transact(self.Cmd.SEND_DATA, data, expected_size = 0)

    def enter_bootloader(self):
        self.frame_send(self.Cmd.SYNC_BOOTLOADER)
        data = self.transact(self.Cmd.ENTER_BOOTLOADER, expected_size = 8)
        silicon_id = int.from_bytes(data[:4], "little")
        silicon_rev = data[4]
        bootloader_version = int.from_bytes(data[5:8], "little")

        return silicon_id, silicon_rev, bootloader_version

    def program_row(self, *, array_id, row_number, data):
        """
        After sending multiple bytes of data to the bootloader using the
        send data command, the last chunk of data is sent along with
        this command.
        """
        data = self.transact(self.Cmd.PROGRAM_ROW, bytes([array_id, row_number & 0xff, row_number >> 8]) + data, expected_size = 0)

    def verify_row(self, *, array_id, row_number):
        """
        Returns the checksum of the specified row
        """
        data = self.transact(self.Cmd.VERIFY_ROW, bytes([array_id, row_number & 0xff, row_number >> 8]), expected_size = 1)
        return data[0]

    def exit_bootloader(self):
        """
        This command is not acknowledged.
        """
        self.frame_send(self.Cmd.EXIT_BOOTLOADER)

    def info_dump(self):
        silicon_id, silicon_rev, bootloader_version = self.enter_bootloader()
        self.logger.note("Silicon ID: %x", silicon_id)
        self.logger.note("Silicon Revision: %x", silicon_rev)
        self.logger.note("Bootloader version: %x", bootloader_version)

        first, last = self.get_flash_size(array_id = 0)
        self.logger.note("Flash range: 0x%04x-0x%04x", first, last)

    def row_program(self, *, array_id, row_number, data):
        assert len(data) == self.row_size
        cs = self.chunk_size

        chunks = [data[x:x+cs] for x in range(0, len(data), cs)]

        for c in chunks[:-1]:
            self.send_data(c)

        self.program_row(array_id = array_id, row_number = row_number, data = chunks[-1])
        chk = self.verify_row(array_id = array_id, row_number = row_number)
        cchk = self.row_checksum(data)
        assert chk == cchk, (hex(chk), hex(cchk))
        
