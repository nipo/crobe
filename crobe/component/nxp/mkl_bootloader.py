from ...model import PortComponent
from ...adapter.protocol import i2c
import binascii
import time
import crcmod

__all__ = ["MklBootloader"]

class MklI2cTransport(PortComponent):
    def __init__(self, bus, saddr):
        PortComponent.__init__(self, bus, "MklI2c")
        self.saddr = saddr
#        self.port.freq_cap("mkl", 100e3)

    def write(self, data):
        self.logger.debug("< %s", binascii.b2a_hex(data))
        self.port.write(self.saddr, data)

    def read(self, size):
        data = self.port.read(self.saddr, size)
        self.logger.debug("> %s", binascii.b2a_hex(data))
        return data

class MklBootloader(PortComponent):
    max_packet_size = 0x10

    def __init__(self, port):
        PortComponent.__init__(self, port, "MklBl")

    @staticmethod
    def crc(blob):
        crc16 = crcmod.mkCrcFun(0x11021, rev=False, initCrc=0, xorOut=0)
        return crc16(blob).to_bytes(2, "little")

    FRAME_START         = 0x5a
    FRAME_ACK           = 0xa1
    FRAME_NAK           = 0xa2
    FRAME_ACK_ABORT     = 0xa3
    FRAME_COMMAND       = 0xa4
    FRAME_DATA          = 0xa5
    FRAME_PING          = 0xa6
    FRAME_PING_RESPONSE = 0xa7

    CMD_FLASH_ERASE_ALL          = 0x01
    CMD_FLASH_ERASE_REGION       = 0x02
    CMD_WRITE_MEMORY             = 0x04
    CMD_FILL_MEMORY              = 0x05
    CMD_FLASH_SECURITY_DISABLE   = 0x06
    CMD_GET_PROPERTY             = 0x07
    CMD_EXECUTE                  = 0x09
    CMD_CALL                     = 0x0a
    CMD_RESET                    = 0x0b
    CMD_SET_PROPERTY             = 0x0c
    CMD_FLASH_ERASE_ALL_UNSECURE = 0x0d
    CMD_FLASH_PROGRAM_ONCE       = 0x0e
    CMD_FLASH_READ_ONCE          = 0x0f
    CMD_FLASH_READ_RESOURCE      = 0x10

    PROPERTY_CURRENT_VERSION       = 0x01
    PROPERTY_AVAILABLE_PERIPHERALS = 0x02
    PROPERTY_FLASH_START_ADDRESS   = 0x03
    PROPERTY_FLASH_SIZE_IN_BYTES   = 0x04
    PROPERTY_FLASH_SECTOR_SIZE     = 0x05
    PROPERTY_FLASH_BLOCK_COUNT     = 0x06
    PROPERTY_AVAILABLE_COMMANDS    = 0x07
    PROPERTY_VERIFY_WRITES         = 0x0A
    PROPERTY_MAX_PACKET_SIZE       = 0x0B
    PROPERTY_RESERVED_REGIONS      = 0x0C
    PROPERTY_VALIDATE_REGIONS      = 0x0D
    PROPERTY_RAM_START_ADDRESS     = 0x0E
    PROPERTY_RAM_SIZE_IN_BYTES     = 0x0F
    PROPERTY_SYSTEM_DEVICE_ID      = 0x10
    PROPERTY_FLASH_SECURITY_STATE  = 0x11

    def frame_send(self, tag, params = b''):
        header = bytes([self.FRAME_START, tag])
        if params or tag not in [self.FRAME_ACK, self.FRAME_NAK, self.FRAME_ACK_ABORT, self.FRAME_PING]:
            header += len(params).to_bytes(2, "little")
            crc = self.crc(header + params)
            blob = header + crc + params
        else:
            blob = header

        self.port.write(blob)

    def frame_receive(self, tag, size):
        r = self.port.read(size)

        if tag == self.FRAME_PING_RESPONSE:
            assert r[0] == self.FRAME_START
            assert r[1] == tag
            assert self.crc(r[:-2]) == r[-2:]
            return r[2:]

        if tag == self.FRAME_COMMAND:
            assert r[0] == self.FRAME_START
            assert r[1] == tag

            length = int.from_bytes(r[2:4], "little")
            crc = r[4:6]
            rsp = r[6:]
            r = r[:length + 6]

            assert self.crc(r[0:4] + rsp) == crc, self.crc(r[0:4] + rsp)

            return rsp

#        r = hdr
        assert r[0] == self.FRAME_START
        assert r[1] == tag

    DELAYS = {
        FRAME_PING: .1,
        FRAME_COMMAND: .1,
        FRAME_DATA: .010,
        }

    def txn_write(self, tag, params, rsp_tag, rsp_frame_size):
        self.logger.debug("txn write %02x %s %02x", tag, params, rsp_tag)
        self.frame_send(tag, params)
        time.sleep(self.DELAYS.get(tag, .1))
        return self.frame_receive(rsp_tag, rsp_frame_size)

    def txn_read(self, tag, size):
        self.logger.debug("txn read %02x", tag)
        time.sleep(.1)
        r = self.frame_receive(tag, size)
        self.frame_send(self.FRAME_ACK)
        return r

    def ping(self):
        time.sleep(.1)
        self.logger.info("ping")
        return self.txn_write(self.FRAME_PING, b'', self.FRAME_PING_RESPONSE, 10)

    def abort(self):
        self.frame_send(self.FRAME_ACK_ABORT)
        for i in range(10):
            try:
                self.ping()
            except i2c.AddressNack:
                continue
            except AssertionError:
                continue
            break

    def command(self, cmd, arg = [], data_pkts = []):
        self.logger.info("command %02x %s %d", cmd, arg, len(data_pkts))
        header = bytes([cmd, 0, 0, len(arg)])
        data = b''.join(a.to_bytes(4, "little") for a in arg)

        self.txn_write(self.FRAME_COMMAND, header + data, self.FRAME_ACK, 2)

        r = self.txn_read(self.FRAME_COMMAND, 18)
        hdr = r[:4]
        response = [int.from_bytes(r[i:i+4], "little") for i in range(4, len(r), 4)]
        assert hdr[3] == len(response)

        self.logger.info(" rsp %02x %s", r[1], response)
        
        if not data_pkts:
            return response

        for d in data_pkts:
            self.txn_write(self.FRAME_DATA, d, self.FRAME_ACK, 2)

        r = self.txn_read(self.FRAME_COMMAND, 18)

        hdr = r[:4]
        response = [int.from_bytes(r[i:i+4], "little") for i in range(4, len(r), 4)]
        assert hdr[3] == len(response)

        return response

    def get_property(self, tag):
        r = self.command(self.CMD_GET_PROPERTY, [tag])
        assert r[0] == 0
        return r[1:]

    def set_property(self, tag, value):
        r = self.command(self.CMD_SET_PROPERTY, [tag, value])
        assert r[0] == 0

    def execute(self, entry_point, arg, stack = 0):
        flash_start, = self.get_property(self.PROPERTY_FLASH_START_ADDRESS)
        flash_size, = self.get_property(self.PROPERTY_FLASH_SIZE_IN_BYTES)
        ram_start, = self.get_property(self.PROPERTY_RAM_START_ADDRESS)
        ram_size , = self.get_property(self.PROPERTY_RAM_SIZE_IN_BYTES)
        assert entry_point & 1
        assert flash_start <= entry_point < flash_start + flash_size
        assert not stack or (ram_start <= stack < ram_start + ram_size)
        self.command(self.CMD_EXECUTE, [entry_point, arg, stack])

    def mem_write(self, addr, blob, chunk_size = 0x8):
        chunks = [blob[i:i+chunk_size] for i in range(0, len(blob), chunk_size)]
        return self.command(self.CMD_WRITE_MEMORY, [addr, len(blob)], chunks)

    def start(self):
        for i in range(2):
            try:
                self.ping()
            except i2c.AddressNack:
                pass
            except AssertionError:
                pass
        self.max_packet_size, = self.get_property(self.PROPERTY_MAX_PACKET_SIZE)

    def info_dump(self):
        ver, = self.get_property(1)
        print("Bootloader version: %x" % ver)

        flash_start, = self.get_property(self.PROPERTY_FLASH_START_ADDRESS)
        print("Flash start: 0x%08x" % flash_start)
        flash_size, = self.get_property(self.PROPERTY_FLASH_SIZE_IN_BYTES)
        print("Flash size: 0x%08x" % flash_size)
        commands, = self.get_property(self.PROPERTY_AVAILABLE_COMMANDS)
        print("Available commands: %s" % [i+1 for i in range(16) if commands & (1 << i)])
        ram_start, = self.get_property(self.PROPERTY_RAM_START_ADDRESS)
        print("Ram start: 0x%08x" % ram_start)
        ram_size , = self.get_property(self.PROPERTY_RAM_SIZE_IN_BYTES)
        print("Ram size: 0x%08x" % ram_size)

        commands, = self.get_property(self.PROPERTY_AVAILABLE_COMMANDS)
        print("Available commands: %s" % [i+1 for i in range(16) if commands & (1 << i)])

@i2c.Interface.db.register("mkl")
def mkl_reg(bus):
    tr = MklI2cTransport(bus, 0x10)
    return MklBootloader(tr)
