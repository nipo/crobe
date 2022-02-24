from ..model import PortComponent
from .model import Bus
from ..db import Db, NoMatch, InitializationFailure
from ..protocol import spi
from ..util.pretty import base2, metric
from ..jep106 import name_get
import binascii
import struct
import time

__all__ = ["SpiFlash"]

@spi.Target.db.register("flash")
@spi.Target.db.register("memory")
def spi_flash_probe(target, *args):
    return SpiMemory.detect(target)

class SpiMemory(PortComponent, Bus):
    max_freq = 33e6
    
    total_size = 0

    ADDRESS_SIZE = 3

    db = Db("SPI memory type")

    CMD_FAST_READ = b"\x0b"
    CMD_READ_JEDEC_ID = b"\x9f"
    CMD_RESET_ENABLE = b'\x66'
    CMD_RESET = b'\x99'

    write_buffer_size = 1
    
    def __init__(self, port, idr = 0, name = "SPI Flash"):
        PortComponent.__init__(self, port, name)
        Bus.__init__(self, self.name)
        if not idr:
            idr = self.idr_get()
        self.idr = idr
        self.logger.info("SPI flash with IDR=%06x", self.idr)

    @property
    def page_size(self):
        return self.write_buffer_size

    def mem_read(self, address, size):
        return self.read(address, size)

    def mem_write(self, address, data):
        return self.write(address, data)

    @classmethod
    def detect(cls, port):
        port.execute([
            port.cmd_cs(False),
            port.cmd_shift(b'\x00', read_miso = False),
            ])
        time.sleep(.01)
        port.execute([
            port.cmd_cs(True),
            port.cmd_shift(b'\xab', read_miso = False),
            port.cmd_cs(False),
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
        port.execute([
            port.cmd_cs(True),
            port.cmd_shift(b'\xf0', read_miso = False),
            port.cmd_cs(False),
            ])
        time.sleep(.3)

        sfdp = port.cmd_shift(4)
        idr = port.cmd_shift(0x13)

        cmds = [port.cmd_cs(True),
                port.cmd_shift(b"\x9f", read_miso = False),
                idr,
                port.cmd_cs(False),
                port.cmd_shift(b'\x00', read_miso = False),
                port.cmd_cs(True),
                port.cmd_shift(b"\x5a\x00\x00\x00\x00", read_miso = False),
                sfdp,
                port.cmd_cs(False),
                ]
        port.execute(cmds)

        sfdp = sfdp.miso
        id_cfi = idr.miso[0x10:0x13]
        idr = int.from_bytes(idr.miso[:3], "big")
        port.logger.info("IDR: 0x%06x", idr)
        port.logger.info("SFDP: %s", sfdp)
        
        if idr in [0, 0xffffff, 0x9f0000, 0x9fffff]:
            raise InitializationFailure("Bad SPI IDR: 0x%06x" % idr)

        try:
            self = cls.db.call(idr, port, idr)
        except NoMatch:
            self = None
        
        if self is None and sfdp == b'SFDP':
            self = SfdpFlash(port, idr)

        if self is None and id_cfi == b'QRY':
            self = IdCfiFlash(port, idr)

        if self is None:
            raise NoMatch("SPI flashes", idr)
        
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

    def command(self, cmd, arg = b'', wdata = b'', rsize = 0, dummy_words = 0):
        cmds = [self.port.cmd_cs(True),
                self.port.cmd_shift(cmd, read_miso = False)]
        if arg:
            cmds.append(self.port.cmd_shift(arg, read_miso = False))
        if dummy_words:
            cmds.append(self.port.cmd_shift(b"\xff"*dummy_words, read_miso = False))
        if wdata:
            cmds.append(self.port.cmd_shift(wdata, read_miso = False))
        if rsize:
            rsp = self.port.cmd_shift(rsize)
            cmds.append(rsp)
        cmds += [self.port.cmd_cs(False)]
        self.logger.protocol("<< %s %s %s %d", cmd.hex(), arg.hex(), wdata.hex(), rsize)
        self.port.execute(cmds)
        if rsize:
            self.logger.protocol(">> %s", rsp.miso.hex())
            return rsp.miso
        self.logger.protocol(">> -")
        return b''
        
    def idr_get(self):
        return int.from_bytes(self.command(self.CMD_READ_JEDEC_ID, rsize = 3), byteorder = 'big')

    def addr(self, value):
        return value.to_bytes(self.ADDRESS_SIZE, byteorder = "big")
    
    def read(self, address, size, op = None):
        if op is None:
            op = self.CMD_FAST_READ
        return self.command(op, arg = self.addr(address), rsize = size, dummy_words = 1)

    def verify(self, program):
        si = self.SECTOR_INFO[0]

        for page in program.paged(si["size"], fill = b'\x00'):
            if self.read(page.address, len(page)) != page.data:
                return False
        return True

class SpiFlash(SpiMemory):
    CMD_PAGE_PROGRAM = b"\x02"
    CMD_WRITE_STATUS = None
    CMD_WRITE_VOLATILE_STATUS = None
    CMD_CHIP_ERASE = b'\xc7'
    CMD_WRITE_ENABLE = b'\x06'
    CMD_WRITE_DISABLE = b'\x04'
    CMD_READ_STATUS = b'\x05'
    STATUS_WIP = 1
    STATUS_WEL = 2
    SECTOR_INFO = []

    def info(self):
        self.logger.info("Total size: %s (%s)", base2(self.total_size, "B"), base2(self.total_size * 8, "b"))
        self.logger.note("%d bytes address, %d-byte write buffer", self.ADDRESS_SIZE, self.write_buffer_size)
        self.logger.note("Fast read: %02x, Page program: %02x, erase commands:", self.CMD_FAST_READ[0], self.CMD_PAGE_PROGRAM[0])
        for s in self.SECTOR_INFO:
            self.logger.note("- type %d: %d x %s sectors, erase command: %s",
                             s["type"], self.total_size / s["size"], base2(s["size"], 'B'),
                             ("0x%02x" % s["erase_cmd"][0]) if s["erase_cmd"] else "-")
        if self.CMD_WRITE_VOLATILE_STATUS:
            self.logger.note("Volatile status write op: 0x%02x", self.CMD_WRITE_VOLATILE_STATUS[0])

    def write_enable(self, enable):
        retries = 0
        while bool(self.status & self.STATUS_WEL) != enable:
            if enable:
                self.logger.trace("Write enable (%02x)", self.CMD_WRITE_ENABLE[0])
                self.command(self.CMD_WRITE_ENABLE)
            else:
                self.logger.trace("Write disable (%02x)", self.CMD_WRITE_DISABLE[0])
                self.command(self.CMD_WRITE_DISABLE)
            retries += 1

            if retries & 0xff == 0:
                self.logger.warning("Still waiting for WEL to get %s, status = 0x%02x", enable, self.status)

    @property
    def status(self):
        st = self.command(self.CMD_READ_STATUS, rsize = 1)[0]
#        self.logger.trace("Status: %02x", st)
        return st

    def status_write(self, *values):
        assert self.CMD_WRITE_STATUS is not None
        self.write_enable(True)
        self.command(self.CMD_WRITE_STATUS, arg = bytes(values), rsize = 0)

    def unprotect(self):
        if self.CMD_WRITE_STATUS:
            self.status_write(0)
        
    def erase_all(self):
        self.unprotect()
        self.write_enable(True)
        self.logger.trace("Chip erase (%02x)", self.CMD_CHIP_ERASE[0])
        self.command(self.CMD_CHIP_ERASE)
        self.logger.trace("Waiting for erase to complete")
        while self.status & self.STATUS_WIP:
            time.sleep(.1)
        self.write_enable(False)
    
    def erase(self, base, size):
        self.logger.trace("Erasing %08x, %s", base, base2(base+size, 'B'))

        chosen = None
        while size > 0:
            try_again = False
            for i, s in enumerate(self.SECTOR_INFO):
                if not s["erase_cmd"]:
                    continue
                ss = s["size"]
                if base % ss == 0 and size <= ss == 0:
                    chosen = s

            if not chosen:
                try_again = True
                chosen = self.SECTOR_INFO[0]
                assert base % chosen["size"] == 0 and chosen["erase_cmd"]

            for addr in range(base, base + size, chosen["size"]):
                self.erase_sector(addr, chosen)
                base += chosen["size"]
                size -= chosen["size"]
                if try_again:
                    break

            chosen = None

    def erase_sector(self, addr, si):
        self.unprotect()
        self.write_enable(True)
        self.logger.trace("Erasing %d bytes at %08x (%02x)", si["size"], addr, si["erase_cmd"][0])
        self.command(si["erase_cmd"], arg = self.addr(addr))
        while self.status & self.STATUS_WIP:
            pass

    def page_program(self, addr, data):
        self.write_enable(True)
        self.command(self.CMD_PAGE_PROGRAM, arg = self.addr(addr), wdata = data)
        while self.status & self.STATUS_WIP:
            time.sleep(.01)
        
    def write_chunk(self, addr, data):
        for retry in range(10):
            self.page_program(addr, data)

            readback = self.read(addr, len(data))
            if readback == data:
                return

            unrecoverable = [x & ~y for (x, y) in zip(data, readback)]
            if any(unrecoverable):
                raise RuntimeError("Unrecoverable bitflips !")
        raise RuntimeError("Unrecoverable bad write !")

    def _write(self, base, data):
        write_chunk_size = self.write_buffer_size
        offset = 0

        while offset < len(data):
            self.logger.trace("Writing chunk at 0x%08x... (%02x)", base + offset, self.CMD_PAGE_PROGRAM[0])

            alignment = (base + offset) % write_chunk_size
            size = write_chunk_size - alignment

            self.write_chunk(base + offset, data[offset : offset + size])
            offset += size

        self.write_enable(False)

    def write(self, base, data):
        s = len(data)
        si = [si for si in self.SECTOR_INFO if si["size"] == s]
        if si:
            si, = si
            for retry in range(3, -1, -1):
                try:
                    return self._write(base, data)
                except:
                    if retry == 0:
                        raise
                self.erase_sector(base, si)
        else:
            return self._write(base, data)

class SpiPSRam(SpiMemory):
    CMD_WRITE = b"\x02"

    def info(self):
        self.logger.info("Fast read: %02x, Write: %02x", self.CMD_FAST_READ[0], self.CMD_WRITE[0])

    def erase(self, base, size):
        self.write(base, b"\xff" * size)

    def write(self, base, data):
        for off in range(0, len(data), self.write_buffer_size):
            blob = data[off:][:self.write_buffer_size]
            self.command(self.CMD_WRITE, arg = self.addr(base + off), wdata = blob)

class SelfDescriptiveFlash(SpiFlash):
    def __init__(self, port, idr, name):
        SpiFlash.__init__(self, port, idr, name)

    def _id_cfi_parse(self, data):
        for off in range(0, len(data), 16):
            self.logger.info("ID-CFI %04x %s", off, binascii.b2a_hex(data[off:off+16]))
        assert data[0x10:0x13] == b"QRY"

        si = []
        self.total_size = 1 << data[0x27]
        wbs_l2 = int.from_bytes(data[0x2a:0x2c], "little")
        self.logger.info("WBS l2: %d", wbs_l2)
        if wbs_l2 == 0:
            self.write_buffer_size = 256
        else:
            self.write_buffer_size = 1 << wbs_l2
            
        for i in range(data[0x2c]):
            y, z = struct.unpack("<HH", data[0x2d + 4 * i: 0x2d + 4 * i + 4])
            block_size = z * 256
            region_size = block_size * (y + 1)
            si.append(dict(size = region_size, type = i+1, erase_cmd = None))
        if not self.SECTOR_INFO:
            self.SECTOR_INFO = si

class IdCfiFlash(SelfDescriptiveFlash):
    def __init__(self, port, idr, name = "ID-CFI Flash"):
        SelfDescriptiveFlash.__init__(self, port, idr, name)

        hdr = self.command(self.CMD_READ_JEDEC_ID, rsize = 4)
        length = hdr[3]

        id_cfi_blob = self.command(self.CMD_READ_JEDEC_ID, rsize = 4 + (length or 0x100))

        self._id_cfi_parse(id_cfi_blob)

class SfdpFlash(SelfDescriptiveFlash):
    CMD_SFDP_READ = b'\x5a'

    def __init__(self, port, idr, name = "SFDP Flash"):
        SelfDescriptiveFlash.__init__(self, port, idr, name)
        self.__address_4byte_support = False

        sfdp_header = self.sfdp_read(0, 8)
        if not sfdp_header.startswith(b'SFDP'):
            raise ValueError("Bad SFDP header", sfdp_header)
        header_count = sfdp_header[6] + 1

        self.logger.info("SFDP v%d.%d header found, %d NPH", sfdp_header[5], sfdp_header[4], header_count)

        headers = self.sfdp_read(8, header_count * 8)

        sfdp_desc = None, None
        four_byte = None
        id_cfi = None
        
        for i in range(header_count):
            jid, minor, major, length, ptp = struct.unpack("<BBBBL", headers[i * 8: (i+1)*8])
            jid |= (ptp & 0xff000000) >> 16
            ptp = ptp & 0xffffff
            self.logger.info("- %d ID 0x%04x v%d.%d at %08x, %d bytes",
                             i, jid, major, minor, ptp, length * 4)

            data = self.sfdp_read(ptp, length * 4)
            #self.logger.info("  data: %s", binascii.b2a_hex(data))
            
            if jid & 0xff00 == 0xff00:
                # JEDEC std
                if jid == 0xff00:
                    if sfdp_desc[0] is None or sfdp_desc[0] < (major, minor):
                        sfdp_desc = (major, minor), data
                elif jid == 0xff81:
                    if major == 1 and minor == 0:
                        self._sector_map_parse(data)
                        continue
                elif jid == 0xff84:
                    if major == 1 and minor == 0:
                        four_byte = data
                        continue

                self.logger.debug("    Data: %s", binascii.b2a_hex(data))
                continue

            self.logger.info("    Vendor data: %s", name_get((jid >> 8) - 1, jid & 0x7f))

            if jid == 0x0101:
                if major == 1 and minor == 1:
                    id_cfi = data
            else:
                self.logger.info("    Data: %s", binascii.b2a_hex(data))

        if sfdp_desc[0] is not None:
            (major, minor), data = sfdp_desc
            if major == 1 and minor <= 5:
                self._sfdp_1_5_parse(data)
            elif major == 1 and minor == 6:
                self._sfdp_1_6_parse(data)
            else:
                self.logger.warning("Unsupported SFDP version: %d.%d" % (major, minor))

        if four_byte:
            self._4byte_addr_insts_parse(four_byte)

        if id_cfi:
            self._id_cfi_parse(id_cfi)
                
        if self.total_size > (1 << (self.ADDRESS_SIZE * 8)):
            self.total_size = 1 << (self.ADDRESS_SIZE * 8)
            self.logger.warning("Only lower %s accessible with %d-byte addresses",
                                base2(self.total_size, "B"), self.ADDRESS_SIZE)

    def _sector_map_parse(self, data):
        for offs in range(0, len(data), 8):
            chunk = data[offs: offs + 8]
            map_desc = bool(chunk[0] & 2)
            last = bool(chunk[0] & 1)

            self.logger.note("  - Command/Map %s", binascii.b2a_hex(chunk))

            if map_desc:
                _, cmd_instr, len_lat, mask, address = struct.unpack("<BBBBL", chunk)
                length = len_lat >> 6
                lat = len_lat & 0xf

                self.logger.note("  - Command descriptor mask %02x len %x lat %x cmd %02x, addr %08x",
                                 mask, length, lat, cmd_instr, address)
            else:
                _, cid, rcount, _, etype_size = struct.unpack("<BBBBL", chunk)
                etype = etype_size & 0xf
                size = etype_size >> 8

                self.logger.note("  - Map descriptor id %d rcount %d erase %x size %d",
                                 cid, rcount + 1, etype, size)

            if last:
                break

    def _4byte_addr_insts_parse(self, data):
        if not self.__address_4byte_support:
            return

        support, erase_cmd = struct.unpack("<L4s", data)
        # Check for 1-1-1 command set
        # Bit 1: Fast read 1-1-1, cmd 0ch
        # Bit 6: Page program 1-1-1, cmd 12h
        # Bit 9-12: Erase for type 1-4
        mask = 0x42
        for i in [x["type"] for x in self.SECTOR_INFO]:
            mask |= 1 << (8 + i) #type is 1-based

        self.logger.note("  - 4-byte address command info support %06x, expecting %06x", support, mask)

        if (support & mask) == mask:
            self.ADDRESS_SIZE = 4
            self.CMD_FAST_READ = b"\x0c"
            self.CMD_PAGE_PROGRAM = b"\x12"
            for si in self.SECTOR_INFO:
                si["erase_cmd"] = erase_cmd[si["type"] - 1:si["type"]]
            self.logger.info("  - Successful discovery of 4-byte address commands")

    def _sfdp_1_5_parse(self, data):
        if data[0] & 3 == 1:
            self.block_size = 4096
        if data[0] & 0x8:
            self.CMD_WRITE_VOLATILE_STATUS = "\x06" if data[0] & 0x10 else "\x50"
        if data[1] != 0xff:
            self.CMD_4KB_ERASE = bytes([data[1]])
        if data[2] & 0x6 == 0:
            self.ADDRESS_SIZE = 3
        elif data[2] & 0x6 == 2:
            self.__address_4byte_support = True

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
            self.SECTOR_INFO.append({"size": 1 << s, "erase_cmd": op, "type": i+1})

    def _sfdp_1_6_parse(self, data):
        self._sfdp_1_5_parse(data)
        self.logger.info("SFDP1.6 WBS: 0x%02x", data[0x28])
        self.write_buffer_size = 2**(data[0x28]>>4)
        
    def sfdp_read(self, offset, size):
        return self.command(self.CMD_SFDP_READ,
                            arg = offset.to_bytes(3, byteorder = 'big'),
                            dummy_words = 1,
                            rsize = size)
