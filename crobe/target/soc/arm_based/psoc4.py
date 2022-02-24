from ....part_id import PartId
from ....puppet import Puppet, Zone
from ....util.allocator import Allocator
from ....component.arm.cortex import Cortex
from ....component.arm.dp import DpAccessFailure
from ....component.cypress.cybl import CyBl
from ....model import PortComponent
from ... import memory, model
from .soc import SoC, BusRam
import time
import binascii

class PSoC4Flash(memory.Flash):
    def __init__(self, name, address, size, page_size, soc):
        memory.Flash.__init__(self, name, address, size, page_size)
        self.soc = soc

    def read(self, offset, size):
        return self.soc.bus.mem_read(self.address + offset, size)

    def erase(self, offset, size):
        self.logger.warning("Cannot blank region")

    def write(self, offset, data):
        macro_size = self.soc.FLASH_ROW_SIZE * self.soc.FLASH_ROW_COUNT

        delta = 0
        while delta < len(data):
            base = offset + delta

            macro = base // macro_size
            row = (base % macro_size) // self.soc.FLASH_ROW_SIZE
            boff = base % self.soc.FLASH_ROW_SIZE

            size = self.soc.FLASH_ROW_SIZE - boff

            chunk = data[base - offset : base - offset + size]

            self.soc.srom.flash_write_row(macro, row, boff, chunk)

            delta += len(chunk)

class SromTimeout(Exception):
    pass

class SromError(Exception):
    CODES = {
        0x01: "Permission denied",
        0x02: "Index error",
        0x03: "Value error",
        0x04: "Bad rowID",
        0x05: "Protected row",
        0x07: "Resume done already",
        0x08: "Resume pending",
        0x09: "Resume busy",
        0x0a: "Flash erase failed",
        0x0b: "Bad call",
        0x0c: "Key mismatch",
        0x0e: "Invalid address",
        0x0f: "No scratchpad",
        0x12: "Bad clock state",
        0x13: "Clock already OK",
        }

    def __init__(self, code):
        self.code = code
        self.message = self.CODES.get(code)
        Exception.__init__(self, self.code, self.message)

class PSoC4Srom(PortComponent):
    # http://dmitry.gr/index.php?r=05.Projects&proj=24.%20PSoC4%20confidential
    Get_Silicon_ID               = 0x00
    Write_NVL_byte               = 0x01
    Load_NV_latches_from_HW      = 0x02
    Read_NVL_byte                = 0x03
    Load_Flash_Bytes             = 0x04
    Write_Row                    = 0x05
    Program_Row                  = 0x06
    Nonblocking_Write_Row        = 0x07
    Nonblocking_Program_Row      = 0x08
    Nonblocking_Resume           = 0x09
    Erase_All                    = 0x0a
    Checksum                     = 0x0b
    Flash_Analog_Read            = 0x0c
    Write_Protection             = 0x0d
    Memset_Word                  = 0x0e
    Copy_Some_Code_to_Ram        = 0x0f
    Flash_Analog_Read_Mode_Enter = 0x11
    Flash_Analog_Read_Mode_Exit  = 0x12
    Init_Chip                    = 0x13
    Config_Flash_Clock           = 0x15
    Read_Clock_Regs              = 0x16
    Clocks_Manual_Setup          = 0x17
    Write_Sflash_Row             = 0x18
    Chip_Reset                   = 0x1b

    CPUSS_SROM_KEY       = 0x0000d3b6
    CPUSS_SYSREQ_REQ     = 0x80000000
    CPUSS_SYSREQ_HMASTER = 0x40000000
    CPUSS_SYSREQ_ROMEN   = 0x20000000
    CPUSS_SYSREQ_PRIV    = 0x10000000

    CPUSS_ST_OK       = 0xa

    def __init__(self, soc):
        PortComponent.__init__(self, soc, "srom")
        ram = soc.children_of_class(memory.Ram)[0]
        self.soc = soc
        self.bus = soc.bus
        self.cpu, = soc.children_of_class(Cortex)
        self.pc = self.cpu.register_by_number[15]
        self.allocator = Allocator(ram.address, 0x100)
        self.trampoline = self.allocator.allocate(4, 4)
#        self.cpu.halt()

    def allocate(self, size, align = 1):
        return Zone(self.bus, self.allocator.allocate(size, 4))
        
    def unallocate(self, zone):
        self.allocator.free(zone.range)

    def state_dump(self, pfx = ""):
        cmds = [
            self.bus.cmd_u32_read(self.soc.CPUSS_SYSREQ),
            self.bus.cmd_u32_read(self.soc.CPUSS_SYSARG),
            ]
        self.bus.execute(cmds)
        self.soc.logger.info("%s Req: %08x, Arg: %08x, cpu: %s, PC %08x", pfx,
                             cmds[0].data, cmds[1].data, self.cpu.state,
                             self.cpu.reg_read([self.pc])[self.pc])

        return cmds[0].data, cmds[1].data

    def req_wait(self, clear_mask, timeout = 1.):
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.bus.u32_read(self.soc.CPUSS_SYSREQ) & clear_mask
            if st == 0:
                return

        self.state_dump("Stuck in command")
        raise SromTimeout()

    def srom_call(self, no, arg):
        self.state_dump("State before")

        self.cpu.reg_write({self.pc: self.trampoline.address | 1})
        self.bus.u32_write(self.trampoline.address, 0xe7fee7fe)
        self.cpu.resume()

        self.state_dump("State once resumed")

        self.soc.logger.debug("SROM call req 0x%02x arg %08x",
                             no, arg)
        cmds = [
            self.bus.cmd_u32_write(self.soc.CPUSS_SYSARG, arg),
            self.bus.cmd_u32_write(self.soc.CPUSS_SYSREQ, 0x80000000 | no),
            ]
        self.bus.execute(cmds)
        self.req_wait(self.CPUSS_SYSREQ_REQ | self.CPUSS_SYSREQ_PRIV)
        self.cpu.halt()

        req, arg = self.state_dump("State after")

        st = arg >> 28
        if st != self.CPUSS_ST_OK:
            raise SromError(arg & 0xff)

        return arg, req

    def keyed_call(self, no, args = 0):
        self.logger.protocol("Keyed Call to %02x", no)
        if isinstance(args, list):
            args = args[:]
            args[0] = (args[0] << 16) | (self.CPUSS_SROM_KEY + (no << 8))
            blob = b''.join(a.to_bytes(4, "little") for a in args)

            z = self.allocate(len(blob), 4)
            z.write(blob)

            self.soc.logger.debug("SROM arg blob at %08x: %s",
                                 z.address, binascii.b2a_hex(blob))

            arg = z.address
        else:
            z = None
            arg = (self.CPUSS_SROM_KEY + (no << 8)) | (args << 16)

        try:
            return self.srom_call(no, arg)
        finally:
            if z is not None:
                self.unallocate(z)

    def silicon_id_get(self):
        arg, req = self.keyed_call(self.Get_Silicon_ID)
        family = req & 0xfff
        prot = (req >> 12) & 0xf
        sid = arg & 0xffff
        minor = (arg >> 16) & 0xf
        major = (arg >> 20) & 0xf

        return family, sid, major, minor, prot

    def flash_write_row(self, macro, rowid, byte_offset, blob):
        if not blob:
            return
        if len(blob) > self.soc.FLASH_ROW_SIZE:
            raise ValueError("Max row size exceeded")
        if byte_offset + len(blob) > self.soc.FLASH_ROW_SIZE:
            raise ValueError("Blob crossing row boundary")

        args = [(macro << 8) | byte_offset, len(blob)-1] + [
            int.from_bytes(blob[x:x+4], "little")
            for x in range(0, len(blob), 4)]
        self.soc.logger.trace("Loading %d bytes to macro %d, row %d offset %d",
                             len(blob), macro, rowid, byte_offset)
        self.keyed_call(self.Load_Flash_Bytes, args)
        self.keyed_call(self.Program_Row, [rowid])

    def erase_all(self):
        self.keyed_call(self.Erase_All, [0])

    def protection_open(self):
        self.keyed_call(self.Write_Protection, 1)

    def set_imo_48m(self):
        self.keyed_call(self.Config_Flash_Clock)

    def reset(self):
        no = self.Chip_Reset
        args = 0
        arg = (self.CPUSS_SROM_KEY + (no << 8)) | (args << 16)

        self.state_dump("State before")

        self.cpu.reg_write({self.pc: self.trampoline.address | 1})
        self.bus.u32_write(self.trampoline.address, 0xe7fee7fe)
        self.cpu.resume()

        self.state_dump("State once resumed")

        self.soc.logger.info("SROM call req 0x%02x arg %08x",
                             no, arg)
        cmds = [
            self.bus.cmd_u32_write(self.soc.CPUSS_SYSARG, arg),
            self.bus.cmd_u32_write(self.soc.CPUSS_SYSREQ, 0x80000000 | no),
            ]
        self.bus.execute(cmds)
        
class PSoC4(SoC):
    def __init__(self, name, port):
        SoC.__init__(self, name, port)
        self.child_add(PSoC4Flash("code", 0, self.flash_size, self.FLASH_ROW_SIZE, self))
        self.child_add(BusRam("ram", 0x20000000, self.ram_size, self.buses[0]))

        self.srom = PSoC4Srom(self)

    def start(self):
        self.bus.u32_write(self.TEST_MODE, 0x80000000)
        assert self.bus.u32_read(self.TEST_MODE) & 0x80000000

        self.srom.req_wait(self.srom.CPUSS_SYSREQ_PRIV)
        
        try:
            self.srom.set_imo_48m()
        except SromError as e:
            if e.code != 0x13:
                raise

        family, sid, major, minor, prot = self.srom.silicon_id_get()
        self.logger.info("MCU Family %02x SiliconID: %4x r%d.%d, prot: %x",
                         family, sid, major, minor, prot)
        SoC.start(self)

    def erase_all(self):
        self.attach()
        pl = self.protection_level
        self.logger.info("Protection level: %d", pl)
        if pl > 1:
            self.srom.protection_open()
        else:
            self.srom.erase_all()

    def program_begin(self, do_erase, assume_clean):
        self.attach()
        if do_erase:
            self.erase_all()
        if assume_clean:
            self.force_blank()

    def write(self, program,
              do_erase = False,
              do_verify = False,
              do_start = False,
              assume_clean = False):
        flash, = self.children_of_class(PSoC4Flash)
        program = program.within(flash.address, flash.address + flash.size)

        SoC.write(self, program, do_erase, do_verify, do_start, assume_clean)

#        assert do_erase
#
#        self.attach()
#        flash, = self.children_of_class(PSoC4Flash)
#
#        data = program.within(flash.address, flash.address + flash.size)
#        pages = list(data.paged(flash.page_size))
#
#        with click.progressbar(pages, label = "Writing flash") as bar:
#            for p in bar:
#                flash.write(p.address - flash.address, p.data)

    @property
    def protection_level(self):
        family, sid, major, minor, prot = self.srom.silicon_id_get()
        return prot

    def reset(self):
        if self.attached:
            self.srom.reset()
        else:
            return SoC.reset(self)

    def attach(self):
        self.logger.trace("psoc4 attach, %s", self.attached)

        if self.attached:
            return

        SoC.attach(self)
        cpu, = self.children_of_class(Cortex)
        cpu.halt()

        self.srom.set_imo_48m()

@SoC.db.register(PartId(0, 0x34, 0x9e)) # CYBL10563-56LQXI
class CyBL(PSoC4):
    ram_size = 8 * 1024
    flash_size = 32 * 1024

    def __init__(self, port):
        PSoC4.__init__(self, "CyBL10563-56LQXI", port)

@SoC.db.register(PartId(0, 0x34, 0xa4))
class CyPD2xxx(PSoC4):
    ram_size       = 4 * 1024

    @property
    def flash_size(self):
        return self.FLASH_MACRO_COUNT * self.FLASH_ROW_COUNT * self.FLASH_ROW_SIZE

    FLASH_ROW_SIZE = 128
    FLASH_ROW_COUNT = 256
    FLASH_MACRO_COUNT = 1

    CPUSS_SYSARG = 0x40100008
    CPUSS_SYSREQ = 0x40100004
    CPUSS_PROTECTION = 0x4010000c
    TEST_MODE    = 0x40030014

    def __init__(self, port):
        PSoC4.__init__(self, "CyPD2xxx", port)

class BootloaderFlash(memory.Region):
    type = memory.Type.FLASH
    flags = set([memory.Flag.WRITABLE, memory.Flag.ERASE_ONE])

    def __init__(self, bl, array_id = 0, offset = 0):
        self.bl = bl
        self.array_id = array_id
        first, last = self.bl.get_flash_size(array_id = 0)
        memory.Flash.__init__(self, "flash_%d"%array_id, offset, bl.row_size * (last+1), bl.row_size)

    def erase(self, offset, size):
        start = offset & ~(self.bl.row_size - 1)
        print(hex(start), hex(offset + size))
        for addr in range(start, offset + size, self.bl.row_size):
            self.bl.erase_row(array_id = self.array_id,
                              row_number = addr // self.bl.row_size)

    def write(self, offset, data):
        assert (offset % self.bl.row_size) == 0
        assert (len(data) % self.bl.row_size) == 0

        rows = [data[x*self.bl.row_size:(x+1)*self.bl.row_size] for x in range(len(data) // self.bl.row_size)]
        for i, row in enumerate(rows):
            self.bl.row_program(array_id = self.array_id,
                                row_number = offset // self.bl.row_size + i,
                                data = row)
            
@model.Target.register(CyBl)
class CyBlTarget(model.Target, memory.Loadable):
    """
    Cypress Analog Coprocessor I2C Bootloader target

    See Cypress Document No. 001-86526
    """

    def __init__(self, comp):
        model.Target.__init__(self, comp.name)
        memory.Loadable.__init__(self)
        self.flash = BootloaderFlash(comp)
        self.child_add(self.flash)
        self.bl = comp
        self.bl.enter_bootloader()

    def program_begin(self, do_erase, assume_clean):
        pass

    def reset(self):
        self.bl.exit_bootloader()
