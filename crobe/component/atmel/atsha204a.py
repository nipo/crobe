from ...protocol import i2c
from ...model import PortComponent
import struct
import time

def crc16(blob):
    crc = 0
    for b in blob:
        for i in range(8):
            append = (b & 0x1) ^ (crc >> 15)
            crc <<= 1
            if append:
                crc ^= 0x8005
            b >>= 1
            crc &= 0xffff
    return crc

@i2c.Interface.db.register("atsha204a")
class AtSha204A(i2c.Slave):
    def __init__(self, bus, saddr = None):
        i2c.Slave.__init__(self, bus, "atsha204a", saddr)
        
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
        self.i2c_write(b"\x01")

    def _read(self, rsize):
        r = self.read(rsize)
        self.logger.debug("< %d %s", rsize, r.hex())
        return r

    def _write_read(self, blob, rsize):
        r = self.write_read(blob, rsize)
        self.logger.debug("<> %s %d %s", blob.hex(), rsize, r.hex())
        return r

    def _write(self, blob):
        self.logger.debug("> %s", blob.hex())
        return self.write(blob)

    def fifo_write(self, blob):
        self._write(b'\x00')
        blob = b'\x03' + blob
        for off in range(0, len(blob), 32):
            self._write(blob[off : off + 32])

    def fifo_read(self, size):
        r = b''
        for off in range(0, size, 32):
            r += self._read(min(32, size - off))
        return r

    def command_execute(self, opcode, param1 = 0, param2 = 0, data = b''):
        self.wake()

        header = struct.pack("<BBBH", 7 + len(data), opcode, param1, param2)
        crc = crc16(header + data).to_bytes(2, "little")
        self.fifo_write(header + data + crc)
        time.sleep(.01)
        t = time.time()
        while time.time() < t + 1:
            try:
                header = self.fifo_read(1)
            except i2c.AddressNack:
                continue
            blob = self.fifo_read(header[0] - 1)
            data = blob[:-2]
            crc = blob[-2:]
            crcc = crc16(header + data).to_bytes(2, "little")
            assert crc == crcc, (crc.hex(), crcc.hex())

            return data

        raise RuntimeError("Command failed")

    def version(self):
        return self.command_execute(0x30)

    def random(self, update_eeprom = False):
        return self.command_execute(0x1b, 0 if update_eeprom else 1)

    def read(self, zone, offset, size):
        if zone == 1:
            read_size = 4
        else:
            read_size = 32
            zone |= 0x80
        start = offset & ~(read_size - 1)
        end = (offset + size + read_size - 1) & ~(read_size - 1)
        s = end - start
        blob = b''
        for o in range(0, s, read_size):
            blob += self.command_execute(0x02, zone, (start + o) // 4)
        print(zone, offset, size, read_size, blob.hex())
        return blob[offset - start : offset - start + size]

    def otp_read(self):
        return self.read(1, 0, 64)
