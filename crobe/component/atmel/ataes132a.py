from ...protocol import i2c
from ...model import PortComponent
from ...util.crc import Crc
import struct
import time
import enum

crc16 = Crc(width = 16, poly = 0x8005, init = 0,
            pop_lsb = False, insert_msb = False,
            complement_input = False, complement_state = False,
            spill_bitswap = False, spill_byte_order = "big")

@i2c.Interface.db.register("ataes132a")
class AtAes132A(i2c.Slave):
    class Command(enum.IntEnum):
        Reset = 0
        Nonce = 1
        Random = 2
        Auth = 3
        EncRead = 4
        EncWrite = 5
        Encrypt = 6
        KeyCreate = 8
        KeyLoad = 9
        Counter = 0xa
        Crunch = 0xb
        Info = 0xc
        Lock = 0xd
        Legacy = 0xf
        BlockRead = 0x10
        Sleep = 0x11
        NonceCompute = 0x13
        AuthCompute = 0x14
        AuthCheck = 0x15
        WriteCompute = 0x16
        DecRead = 0x17
        KeyImport = 0x19
        KeyTransfer = 0x1a

    class ReturnCode(enum.IntEnum):
        Success = 0x00
        BoundaryError = 0x02
        RWConfig = 0x04
        BadAddr = 0x8
        CountErr = 0x10
        NonceError = 0x20
        MacError = 0x40
        ParseError = 0x50
        DataMatch = 0x60
        LockError = 0x70
        KeyErr = 0x80

    class Status(enum.IntEnum):
        Wip = 1
        Wen = 2
        Wakeb = 4
        CRCE = 0x10
        RRdy = 0x40
        EErr = 0x80
        
    def __init__(self, bus, saddr = 0x50):
        i2c.Slave.__init__(self, bus, "ataes132a", saddr)

    @classmethod
    def _ccm_mac(cls, key, nonce, maccount, auth_data, enc_data):
        from Crypto.Cipher import AES
        from Crypto.Util import strxor

        assert len(nonce) == 12

        cbc = AES(key, mode = AES.MODE_CBC,
                  iv = bytes([0x79]) + nonce + bytes([maccount, len(enc_data) >> 8, len(enc_data) & 0xff]))

        ad_clear = bytes([len(auth_data) >> 8, len(auth_data) & 0xff]) + auth_data
        ad_clear += b'\x00' * (-len(ad_clear) % 16)
        auth_clear = cbc.encrypt(ad_clear)

        ctr = AES(key, mode = AES.MODE_CTR,
                  iv = bytes([0x01]) + nonce + bytes([maccount, 0, 0]))

        auth_enc = ctr.encrypt(auth_clear)
        enc_data += b'\x00' * (-len(enc_data) % 16)
        data_enc = ctr.encrypt(enc_data)

        return auth_enc, data_enc

    def start(self):
        i2c.Slave.start(self)
        self.__nonce = None
        self.logger.note("%s", self.command(2, 2))
        self.logger.note("%04x %04x %04x %04x",
                         self.info(0), self.info(5),
                         self.info(6), self.info(0xc))
        self.manufacturing_id = self.block_read(0xf02b, 2)
        self.serial = self.block_read(0xf000, 8)
        self.logger.note("ManufacturingID: %s", self.manufacturing_id.hex())
        self.logger.info("Serial: %s", self.serial.hex())
        key_config = self.block_read(0xf080, 4 * 8)
        key_config2 = self.block_read(0xf0a0, 4 * 8)
        self.key_config = struct.unpack("<" + "L" * 16, key_config + key_config2)
        counters = self.block_read(0xf100, 8 * 4)
        counters2 = self.block_read(0xf120, 8 * 4)
        counters3 = self.block_read(0xf140, 8 * 4)
        counters4 = self.block_read(0xf160, 8 * 4)
        counters = counters + counters2 + counters3 + counters4
        self.counters = [int.from_bytes(counters[x:x+8], "little") for x in range(0, 128, 8)]

        self.logger.note("Key config: %s", ', '.join(map(hex, self.key_config)))
        self.logger.note("Counters: %s", ', '.join(map(hex, self.counters)))

        for i in range(16):
            try:
                self.logger.note("Key %d: %s", i, self.block_read(0xf200 + i * 16, 16))
            except:
                pass
            
        
    @property
    def nonce(self):
        if self.__nonce is None:
            code, data = self.command(self.Command.Nonce, 1, 0, 0, data = b'\x00' * 12)
            if code != 0:
                raise RuntimeError(code)
            self.__nonce = data, 0
        n, i = self.__nonce
        if i < 255:
            self.__nonce = n, i+1
        else:
            self.__nonce = None
        return n, i
        
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

    RESPONSE_ADDR = 0xfe00
    COMMAND_ADDR = 0xfe00
    STATUS_ADDR = 0xfff0
    
    def sleep(self):
        self.command(self.Command.Sleep)

    @property
    def status(self):
        for i in range(10):
            try:
                r = self._read(self.STATUS_ADDR, 1)[0]
            except i2c.AddressNack:
                time.sleep(.01)
                continue
            if r == 0xff:
                time.sleep(.01)
                continue
            return r
        raise RuntimeError("")

    def status_wait(self, inv, end_crit, fail_crit):
        for i in range(30):
            s = self.status ^ inv
            if s & fail_crit:
                raise RuntimeError("Status polling failed", s)
            if s & end_crit:
                return
            time.sleep(.01)
        raise TimeoutError("too long")

    def _read(self, addr, rsize):
        a = addr.to_bytes(2, "big")
        r = self.write_read(a, rsize)
        self.logger.protocol("> %04x %d %s", addr, rsize, r.hex())
        return r

    def _write(self, addr, blob):
        a = addr.to_bytes(2, "big")
        self.logger.protocol("< %04x %s", addr, blob.hex())
        return self.write(a + blob)

    def block_send(self, data):
        header = bytes([len(data) + 3])
        checksum = 0
        blob = crc16.append_to(header + data)
        self._write(self.COMMAND_ADDR, blob)

    def block_receive(self):
        header = self._read(self.RESPONSE_ADDR, 1)
        data_crc = self._read(self.RESPONSE_ADDR, header[0] - 1)
        if not crc16.is_valid(header + data_crc):
            raise ValueError("Bad framing")
        return data_crc[:-2]

    def command_send(self, opcode, mode = 0,
                     param1 = 0, param2 = 0,
                     data = b''):
        header = struct.pack(">BBHH", opcode, mode, param1, param2)
        self.block_send(header + data)

    def response_receive(self):
        block = self.block_receive()
        return_code = self.ReturnCode(block[0])
        data = block[1:]
        return return_code, data

    def command(self, opcode, mode = 0,
                param1 = 0, param2 = 0,
                data = b''):
        self.wake()
        for i in range(10):
            self.command_send(opcode, mode, param1, param2, data)
            if self.status:
                break
            time.sleep(.05)
        self.status_wait(0, self.Status.RRdy,
                         self.Status.EErr | self.Status.CRCE)
        return self.response_receive()

    def block_read(self, address, length):
        assert 1 <= length <= 32
        code, data = self.command(self.Command.BlockRead, 0, address, length)
        if code != self.ReturnCode.Success:
            raise RuntimeError(code)
        return data
    
    def auth(self, mode, ):
        assert 1 <= length <= 32
        code, data = self.command(self.Command.BlockRead, 0, address, length)
        if code != self.ReturnCode.Success:
            raise RuntimeError(code)
        return data
    
    def info(self, index):
        code, data = self.command(self.Command.Info, param1 = index)
        if code != self.ReturnCode.Success:
            raise RuntimeError(code)
        return int.from_bytes(data, "big")

    def random(self, update_eeprom = False):
        code, data = self.command_execute(
            self.Command.Random,
            mode = 0 if update_eeprom else 1)
        if code != self.ReturnCode.Success:
            raise RuntimeError(code)
        return data
    
