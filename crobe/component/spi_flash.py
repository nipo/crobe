from ..model import PortComponent
from ..db import Db, NoMatch
from ..protocol import spi
from ..util.pretty import base2, metric
import binascii
import struct
import time

__all__ = ["SpiFlash"]

class SpiFlash(PortComponent):
    db = Db()

    max_freq = 33e6
    
    total_size = 0
    sector_size = 1
    page_size = 1

    ADDRESS_SIZE = 3
    
    CMD_READ = b"\x0b"
    CMD_READ_JEDEC_ID = b"\x9f"
    CMD_PAGE_PROGRAM = b"\x02"
    CMD_WRITE_STATUS = None
    CMD_CHIP_ERASE = b'\xc7'
    CMD_WRITE_ENABLE = b'\x06'
    CMD_WRITE_DISABLE = b'\x04'
    CMD_READ_STATUS = b'\x05'
    CMD_RESET_ENABLE = b'\x66'
    CMD_RESET = b'\x99'
    STATUS_WIP = 1
    STATUS_WEL = 2
    
    def __init__(self, port, idr = 0, name = "SPI Flash"):
        PortComponent.__init__(self, port, name)
        if not idr:
            idr = self.idr_get()
        self.idr = idr
        self.logger.info("SPI flash, IDR %06x", self.idr)

    def info(self):
        self.logger.info("Total size: %s (%s)", base2(self.total_size, "B"), base2(self.total_size * 8, "b"))
        for i, s in enumerate(self.SECTOR_INFO):
            self.logger.info("- level %d: %d x %s sectors, erase command: 0x%02x",
                             i, self.total_size / s["size"], base2(s["size"], 'B'), s["erase_cmd"][0])
        if self.CMD_WRITE_STATUS:
            self.logger.info("Volatile status write op: 0x%02x", self.CMD_WRITE_STATUS)
           

    @classmethod
    def detect(cls, port):
        port.execute([
            port.cmd_cs(False),
            port.cmd_shift(b'\x00', read_miso = False),
            ])
        time.sleep(.01)
        port.execute([
            port.cmd_cs(True),
            port.cmd_shift(cls.CMD_RESET_ENABLE, read_miso = False),
            port.cmd_cs(False),
            port.cmd_shift(b'\x00', read_miso = False),
            port.cmd_cs(True),
            port.cmd_shift(cls.CMD_RESET, read_miso = False),
            port.cmd_cs(False),
            ])
        time.sleep(.3)
        self = cls(port)
        try:
            self = cls.db.call(self.idr, port, self.idr)
        except NoMatch:
            pass
        self.info()

        self.port.freq_cap(self, self.max_freq)
        self.port.child_add(self)
        return self
        
    def start(self):
        PortComponent.start(self)
        try:
            self.port.reset = False
        except NotImplementedError:
            pass

    def command(self, cmd, size):
        cmds = [self.port.cmd_cs(True), self.port.cmd_shift(cmd, read_miso = False)]
        if size:
            rsp = self.port.cmd_shift(size)
            cmds.append(rsp)
        cmds += [self.port.cmd_cs(False)]
        self.logger.debug("<< %s %d", binascii.b2a_hex(cmd), size)
        self.port.execute(cmds)
        if size:
            self.logger.debug(">> %s", binascii.b2a_hex(rsp.miso))
            return rsp.miso
        self.logger.debug(">> -")

        
    def idr_get(self):
        return int.from_bytes(self.command(self.CMD_READ_JEDEC_ID, 3), byteorder = 'big')

    def addr(self, value):
        return value.to_bytes(self.ADDRESS_SIZE, byteorder = "big")
    
    def read(self, address, size, op = None):
        if op is None:
            op = self.CMD_READ
        return self.command(op + self.addr(address) + b'\x00', size)

    def write_enable(self, enable):
        retries = 0
        while bool(self.status & self.STATUS_WEL) != enable:
            if enable:
                self.command(self.CMD_WRITE_ENABLE, 0)
            else:
                self.command(self.CMD_WRITE_DISABLE, 0)
            retries += 1

            if retries & 0xff == 0:
                self.logger.warning("Still waiting for WEL to get %s, status = 0x%02x", enable, self.status)

    @property
    def status(self):
        return self.command(self.CMD_READ_STATUS, 1)[0]
            
    def erase_all(self):
        self.write_enable(True)
        self.command(self.CMD_CHIP_ERASE, 0)
        while self.status & self.STATUS_WIP:
            time.sleep(.1)
            pass
        self.write_enable(False)
    
    def erase(self, base, size):
        chosen = None
        while size > 0:
            try_again = False
            for i, s in enumerate(self.SECTOR_INFO):
                ss = s["size"]
                if base % ss == 0 and size <= ss == 0:
                    chosen = s

            if not chosen:
                try_again = True
                chosen = self.SECTOR_INFO[0]
                assert base % chosen["size"] == 0

            for addr in range(base, base + size, chosen["size"]):
                self.erase_sector(addr, chosen)
                base += chosen["size"]
                size -= chosen["size"]
                if try_again:
                    break

            chosen = None

    def erase_sector(self, addr, si):
        self.write_enable(True)
        self.logger.info("Erasing %d bytes at %08x", si["size"], addr)
        self.command(si["erase_cmd"] + self.addr(addr), 0)
        while self.status & self.STATUS_WIP:
            pass

    def write(self, base, data):
        si = self.SECTOR_INFO[0]

        page_size = si["size"]

        for offset in range(0, len(data), page_size):

            chunk = data[offset : offset + page_size]
            chunk += b"\xff" * ((-len(chunk)) % page_size)

            self.logger.info("Writing page at 0x%08x...", offset)
            for offset2 in range(0, page_size, 256):
                self.write_enable(True)
                self.command(self.CMD_PAGE_PROGRAM + self.addr(base + offset + offset2)
                             + chunk[offset2 : offset2 + 256], 0)
                while self.status & self.STATUS_WIP:
                    pass

        self.write_enable(False)

    def verify(self, program):
        si = self.SECTOR_INFO[0]

        for page in program.paged(si["size"], fill = b'\x00'):
            if self.read(page.address, len(page)) != page.data:
                return False
        return True

@spi.Interface.db.register("flash")
def spi_flash_probe(bus, *args):
    try:
        return SpiFlash.detect(bus)
    except ValueError:
        raise NoMatch("Not a spi flash")
    
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
                if major == 1 and minor <= 5:
                    self._parse_sfdp_1_5(data)
                elif major == 1 and minor == 6:
                    self._parse_sfdp_1_6(data)
                else:
                    raise ValueError("Unsupported SFDP version: %d.%d" % (major, minor))

    def _parse_sfdp_1_5(self, data):
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

        self.page_size = self.SECTOR_INFO[0]["size"]

    def _parse_sfdp_1_6(self, data):
        self.logger.warning("Should add support for SFDP 1.6 !")
        return self._parse_sfdp_1_5(data)
#        raise ValueError("Unsupported SFDP version: 1.6")
        
    def sfdp_read(self, offset, size):
        return self.command(self.CMD_SFDP_READ + offset.to_bytes(3, byteorder = 'big') + b'\x00', size)
