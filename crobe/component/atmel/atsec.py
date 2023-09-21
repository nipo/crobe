from ...protocol import i2c, base
from ...model import PortComponent
from ... import bitfield
from ...util.crc import Crc
import struct
import time
import enum

crc16 = Crc(width = 16, poly = 0x8005, init = 0,
            pop_lsb = True, insert_msb = False,
            complement_input = False, complement_state = False,
            spill_bitswap = False, spill_byte_order = "little")

class CommandFailure(Exception):
    pass

@i2c.Interface.db.register("atsec")
class AtSec(i2c.Slave):
    class Command(enum.IntEnum):
        Info = 0x30
        Random = 0x1b

    class Status(enum.IntEnum):
        Success = 0x00
        MacError = 0x01
        ParseError = 0x03
        EccFault = 0x05
        SelfTestError = 0x07
        ExecutionError = 0x0f
        AfterWake = 0x11
        WatchdogExpire = 0xee
        CommError = 0xff

        def is_error(self):
            return self != 0 and self != 0x11
        
    class Zone(enum.IntEnum):
        Config = 0
        OTP = 1
        Data = 2

    class ConfigAddress(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        offset = bitfield.Field(0, 3)
        block = bitfield.Field(3, 2)

    class OtpAddress(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        offset = bitfield.Field(0, 3)
        block = bitfield.Field(3, 1)

    class DataAddress(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        offset = bitfield.Field(0, 3)
        block = bitfield.Field(8, 4)
        slot = bitfield.Field(3, 4)

    def __init__(self, bus, saddr = None, name = "atsec"):
        i2c.Slave.__init__(self, bus, saddr = saddr, name = name)
            
    def wake(self):
        for i in range(5):
            try:
                self.port.write(0, b'\x00\x00\x00\x00')
            except:
                pass
            try:
                self.port.write(0, b'')
                return
            except:
                pass
        
    def sleep(self):
        self.write(b'\x01')
        
    def start(self):
        super().start()
        rev = self.command_info_revision()
        if rev[:3] == b'\x00\x00\x60':
            if rev[3] == 0x02:
                product = "ATECC608A"
            elif rev[3] == 0x03:
                product = "ATECC608B"
            else:
                product = "ATECC608?"
        elif rev[:3] == b'\x00\x00\x50':
            product = "ATECC508A"
        elif rev[:3] == b'\x00\x02\x00':
            product = "ATSHA204A"
        else:
            product = "unk"
        self.product = product
        self.logger.info("Product: %s (Rev: %s)", product, rev.hex())

    def io_group_send(self, blob):
        data = bytes([len(blob)+3]) + blob
        super().write(b'\x03' + crc16.append_to(data))

    def io_group_recv(self):
        count = super().read(1)
        data_crc = super().read(count[0] - 1)
        if not crc16.is_valid(count + data_crc):
            raise base.CommunicationError("Bad CRC")
        return data_crc[:-2]

    def command_send(self, opcode, param1 = 0, param2 = 0, data = b''):
        self.wake()
        self.logger.protocol("< Command %s 0x%04x 0x%04x %s", opcode, param1, param2, data.hex())
        header = struct.pack("<BBH", opcode, param1, param2)
        self.io_group_send(header + data)

    def response_receive(self):
        data = self.io_group_recv()
        self.logger.protocol("> Response %s", data.hex())
        if len(data) == 1:
            rc = self.Status(data[0])
            if rc.is_error():
                raise CommandFailure(rc)
            return None
        return data
    
    def command_run(self, opcode,
                    param1 = 0, param2 = 0,
                    data = b'', wait_time = None, timeout = 1.0):
        self.command_send(opcode, param1, param2, data)
        if wait_time:
            time.sleep(wait_time)
        deadline = time.time() + timeout
        while True:
            try:
                return self.response_receive()
            except i2c.AddressNack:
                if time.time() > deadline:
                    raise
                time.sleep(.01)
                continue

    def command_info(self, mode, param = 0):
        return self.command_run(self.Command.Info, mode, param)

    def command_info_revision(self):
        return self.command_info(0)

    def command_random(self):
        return self.command_run(self.Command.Random)
