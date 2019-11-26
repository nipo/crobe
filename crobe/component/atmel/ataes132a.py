from ...protocol import i2c
from ...model import PortComponent
import struct
import time
import enum

def crc16(blob, crc = 0):
    for b in blob:
        for i in range(8):
            append = ((b >> 7) & 0x1) ^ (crc >> 15)
            crc <<= 1
            if append:
                crc ^= 0x8005
            b <<= 1
            crc &= 0xffff
    return crc

@i2c.Interface.db.register("ataes132a")
class AtAes132A(PortComponent):
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
        PortComponent.__init__(self, bus, "ataes132a")
        self.saddr = saddr

    def start(self):
        PortComponent.start(self)
        self.logger.info("%s", self.command(2, 2))
        self.logger.info("%04x %04x %04x %04x",
                         self.info(0), self.info(5),
                         self.info(6), self.info(0xc))
        
    def option_set(self, opt):
        k, v = opt.split('=', 1)
        if k == 'saddr':
            self.saddr = int(v, 16)
        else:
            return PortComponent.option_set(self, opt)
        
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
        r = self.port.write_read(self.saddr, a, rsize)
        self.logger.debug("> %04x %d %s", addr, rsize, r.hex())
        return r

    def _write(self, addr, blob):
        a = addr.to_bytes(2, "big")
        self.logger.debug("< %04x %s", addr, blob.hex())
        return self.port.write(self.saddr, a + blob)

    def block_send(self, data):
        header = bytes([len(data) + 3])
        checksum = 0
        crc = crc16(header + data).to_bytes(2, "big")

        self._write(self.COMMAND_ADDR, header + data + crc)

    def block_receive(self):
        header = self._read(self.RESPONSE_ADDR, 1)
        data_crc = self._read(self.RESPONSE_ADDR, header[0] - 1)
        data = data_crc[:-2]
        
        crc = crc16(header + data).to_bytes(2, "big")
        if crc != data_crc[-2:]:
            raise ValueError("Bad framing")
        return data

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
