from ..model import PortComponent
from ..db import Db, NoMatch
from ..adapter.protocol import spi
from ..util.pretty import sci
import binascii
import struct

__all__ = ["SpiFlash"]

class SpiFlash(PortComponent):
    db = Db()

    total_size = 0
    sector_size = 1
    page_size = 1

    ADDRESS_SIZE = 3
    
    CMD_READ = b"\x0b"
    CMD_READ_JEDEC_ID = b"\x9f"
    CMD_WRITE_STATUS = None
    CMD_CHIP_ERASE = b'\xc7'
    CMD_WRITE_ENABLE = b'\x06'
    CMD_WRITE_DISABLE = b'\x04'
    CMD_READ_STATUS = b'\x05'
    STATUS_WIP = 1
    STATUS_WEL = 2
    
    def __init__(self, port, idr = 0, name = "SPI Flash"):
        PortComponent.__init__(self, name, port)
        if not idr:
            idr = self.idr_get()
        self.idr = idr

    def info(self):
        self.logger.info("SPI flash, IDR %06x", self.idr)
        self.logger.info("Total size: %s (%s)", sci(self.total_size, "B"), sci(self.total_size * 8, "b"))
        for i, s in enumerate(self.SECTOR_INFO):
            self.logger.info("- level %d: %d sectors of %d bytes. Erase command: 0x%02x",
                             i, self.total_size / s["size"], s["size"], s["erase_cmd"][0])
        if self.CMD_WRITE_STATUS:
            self.logger.info("Volatile status write op: 0x%02x", self.CMD_WRITE_STATUS)
           

    @classmethod
    def detect(cls, port):
        self = cls(port)
        try:
            self = cls.db.call(self.idr, port, self.idr)
        except NoMatch:
            pass
        self.info()
        return self
        
    def start(self):
        PortComponent.start(self)
        try:
            self.port.reset = False
        except NotImplementedError:
            pass

    def command(self, cmd, size):
        rsp = self.port.cmd_shift(size)
        self.port.execute([self.port.cmd_cs(True),
                           self.port.cmd_shift(cmd, read_miso = False),
                           rsp,
                           self.port.cmd_cs(False)])
        return rsp.miso
        
    def idr_get(self):
        return int.from_bytes(self.command(self.CMD_READ_JEDEC_ID, 3), byteorder = 'big')

    def addr(self, value):
        return value.to_bytes(self.ADDRESS_SIZE, byteorder = "big")
    
    def read(self, address, size, op = None):
        if op is None:
            op = self.CMD_READ
        return self.command(op + self.addr(address) + b'\x00', size)

    def write_enable(self, enable):
        if enable:
            self.command(self.CMD_WRITE_ENABLE, 0)
        else:
            self.command(self.CMD_WRITE_DISABLE, 0)

    @property
    def status(self):
        return self.command(self.CMD_READ_STATUS, 1)[0]
            
    def chip_erase(self):
        while not (self.status & self.STATUS_WEL):
            self.write_enable(True)
        self.command(self.CMD_CHIP_ERASE, 0)
        while self.status & self.STATUS_WIP:
            pass
        self.write_enable(False)
    
    def erase(self, base, size):
        chosen = None
        for s in self.SECTOR_INFO:
            ss = s["size"]
            if base % ss == 0 and size % ss == 0:
                chosen = ss

        if chosen is None:
            raise ValueError("Cannot find a suitable command to erase zone")

        while not (self.status & self.STATUS_WEL):
            self.write_enable(True)

        for addr in range(base, base + size, ss["size"]):
            self.command(ss["erase_cmd"] + self.addr(addr), 0)
            while self.status & self.STATUS_WIP:
                pass

        self.write_enable(False)

    def write(self, base, payload, erase_first = True):
        if erase_first:
            self.erase(base, len(payload))

        while not (self.status & self.STATUS_WEL):
            self.write_enable(True)

        for offset in range(0, len(payload), 256):
            self.command(self.CMD_PAGE_PROGRAM + self.addr(base + offset) + payload[offset : offset + 256], 0)
            while self.status & self.STATUS_WIP:
                pass

        self.write_enable(False)
        
@SpiFlash.db.register_default
class SfdpFlash(SpiFlash):
    CMD_SFDP_READ = b'\x5a'

    def __init__(self, port, idr, name = "SFDP Flash"):
        SpiFlash.__init__(self, port, idr, name)

        sfdp_header = self.sfdp_read(0, 8)
        if not sfdp_header.startswith(b'SFDP'):
            raise ValueError("Bad SFDP header", sfdp_header)
        header_count = sfdp_header[6] + 1

        self.logger.info("SFDP v%d.%d header found, %d NPH", sfdp_header[5], sfdp_header[4], header_count)

        headers = self.sfdp_read(8, header_count * 8)

        for i in range(header_count):
            jid, minor, major, length, ptp = struct.unpack("<BBBBL", headers[i * 8: (i+1)*8])
            ptp = ptp & 0xffffff
            self.logger.info("- %d ID 0x%02x v%d.%d at %08x, %d bytes",
                             i, jid, major, minor, ptp, length * 4)

            data = self.sfdp_read(ptp, length * 4)
            self.logger.info("  data: %s", binascii.b2a_hex(data))
            
            if jid == 0:
                if data[0] & 3 == 1:
                    self.block_size = 4096
                if data[0] & 0x8:
                    self.CMD_WRITE_STATUS = "\x06" if data[0] & 0x10 else "\x50"
                if data[1] != 0xff:
                    self.CMD_4KB_ERASE = bytes([data[1]])
                if data[2] & 0x6 == 0:
                    self.ADDRESS_SIZE = 3
                elif data[2] & 0x6 == 2:
                    self.ADDRESS_SIZE = 4
                density, = struct.unpack("<L", data[4:8])
                if density & 0x80000000:
                    self.total_size = 1 << ((density & 0x7fffffff) - 3)
                else:
                    self.total_size = (density + 1) / 8
                self.SECTOR_INFO = []
                for i in range(4):
                    s = data[28 + 2 * i]
                    op = data[29 + 2 * i:30 + 2 * i]
                    if not s:
                        continue
                    self.SECTOR_INFO.append({"size": 1 << s, "erase_cmd": op})

    def sfdp_read(self, offset, size):
        return self.command(self.CMD_SFDP_READ + offset.to_bytes(3, byteorder = 'big') + b'\x00', size)
