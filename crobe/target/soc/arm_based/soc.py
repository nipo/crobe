from ... import model as target_model
from .. import model
from ....part_id import PartId
from ....component.arm.coresight.rom_table import RomTable
from ....component.arm.coresight.scs import Scs
from ....component.arm.coresight.dbg import Dbg
from ....component.arm.cortex import Cortex
from ....component.arm.sw_dp import SwDp
from ....component.arm.jtag_dp import JtagDp
from ....component.arm.mem_ap import MemAp
from ... import memory
from ....puppet import Puppet
from ....db import Db, NoMatch, DisabledEntry, InitializationFailure
from .puppet_code import crc32_cm0
from ....util.crc import crc32

__all__ = ["SoC", 'ArmMPuppet', 'StubFlash']

class PuppetStub:
    def __init__(self, puppet, code):
        self.puppet = puppet
        self.code = code
        self.zone = self.puppet.allocate(len(code))
        self.cleaned = False

    def call(self, *args, timeout = None):
        self.zone.write(self.code)
        return self.puppet.call(self.zone.address + 1, *args, timeout = timeout)

    def prepare(self, *args):
        self.zone.write(self.code)
        return self.puppet.prepare(self.zone.address + 1, *args)

    def run(self):
        return self.puppet.run()

    def wait(self, timeout = None):
        self.puppet.wait(timeout = timeout)
        r0 = self.puppet.arg_regs[0]
        return self.puppet.cpu.reg_read([r0])[r0]

    def cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        self.puppet.unallocate(self.zone)

    def __del__(self):
        self.cleanup()
    
class ArmMPuppet(Puppet):
    CRC32 = crc32_cm0["memory_crc32"]

    def __init__(self, soc):
        cpu = soc.children_of_class(Cortex)[0]
        ram = soc.children_of_class(memory.Ram)[0]

        Puppet.__init__(self, cpu, ram,
                        pc_reg = cpu.registers[15],
                        sp_reg = cpu.registers[13],
                        arg_regs = cpu.registers[:4],
                        trampoline_code = b'\x01L\xa0\x47\xbe\xbe\xbe\xbe',
        )

    def stub(self, code):
        return PuppetStub(self, code)

class BusRam(memory.Ram):
    def __init__(self, name, address, size, bus):
        memory.Ram.__init__(self, name, address, size)
        self.bus = bus

    def read(self, offset, size):
        return self.bus.mem_read(self.address + offset, size)

    def write(self, offset, data):
        self.bus.mem_write(self.address + offset, data)

class BusFlash(memory.Flash):
    def __init__(self, name, address, size, page_size, bus):
        memory.Flash.__init__(self, name, address, size, page_size)
        self.bus = bus

    def read(self, offset, size):
        return self.bus.mem_read(self.address + offset, size)

class StubFlash(BusFlash):
    def __init__(self, name, base, size, page_size, soc):
        BusFlash.__init__(self, name, base, size, page_size, soc.buses[0])
        self.soc = soc

    def erase(self, offset, size):
        self.soc.attach()
        puppet = self.soc.puppet()
        self.puppet_erase(puppet, self.address + offset, size)

        if size == self.size:
            self.is_blank = True
            
    def write(self, offset, data):
#        assert offset % self.page_size == 0, hex(offset)
        self.soc.attach()

        puppet = self.soc.puppet()
        if not self.is_blank:
            self.puppet_erase(puppet, self.address + offset, len(data))

        self.puppet_write(puppet, {self.address + offset: data})
            
        self.is_blank = False

    def puppet_erase(self, puppet, address, size):
        code = puppet.stub(self.RANGE_ERASE)
        code.call(address, size, self.page_size,
                  timeout = 0.2 + 0.1 * size / self.page_size)

    def puppet_write(self, puppet, pages):
        if not pages:
            return

        write_buffer = None
        other_buffer = None
        code = None
        try:
            code = puppet.stub(self.PAGE_WRITE)
            write_buffer = puppet.allocate(self.page_size, self.page_size)
            try:
                other_buffer = puppet.allocate(self.page_size, self.page_size)
            except:
                other_buffer = None

            running = False
            with self.logger.progress(self.name, len(pages)) as progress:
                for address, data in progress.iterate(sorted(pages.items())):
                    write_buffer.write(data)

                    if running:
                        code.wait(1)
                        running = False

                    code.prepare(address, write_buffer.address, self.page_size)
                    code.run()
                    running = True

                    if other_buffer:
                        other_buffer, write_buffer = write_buffer, other_buffer
                    else:
                        code.wait(1)
                        running = False

                if running:
                    code.wait(1)
        finally:
            if write_buffer:
                puppet.unallocate(write_buffer)
            if other_buffer:
                puppet.unallocate(other_buffer)
            if code:
                code.cleanup()

    def puppet_update(self, puppet, pages):
        valid = set()

        code = puppet.stub(puppet.CRC32)
        with self.logger.progress("Scanning", len(pages)) as progress:
            for address, data in progress.iterate(sorted(pages.items())):
                from_mem = code.call(address, self.page_size)
                crc = crc32(data)
                self.logger.trace("Page at 0x%08x, CRC32=%08x, in mem=%08x",
                                 address, crc, from_mem)
                if from_mem == crc:
                    valid.add(address)
            code.cleanup()

            for a in valid:
                pages.pop(a)

        return self.puppet_write(puppet, pages)

class SoC(model.SoC):
    db = Db("SoC model")

    def __init__(self, name, port):
        model.SoC.__init__(self, name)
        self.port = port
        self.buses = port.children_of_class(MemAp)
        
        idx = 0
        last_rt = None
        for mem_ap in self.buses:
            for s in mem_ap.children_of_class((Scs, Dbg)):
                rt, = port.children_find(lambda x: isinstance(x, RomTable) and s in x.children)
                if rt is not last_rt:
                    rtidx = 0
                self.child_add(Cortex.from_romtable(rt, idx, rtidx))
                rtidx += 1
                idx += 1

        self.bus = self.buses[0]

    def puppet(self):
        return ArmMPuppet(self)

    def reattach(self):
        assert self.attached
        model.SoC.detach(self)

        self.bus.port.port.reset = True
        self.bus.port.port.line_reset()
        self.bus.port.port.reset = False
        self.bus.port.debug_enable(True)
        self.bus.enable()

        self.attach()

    def attach(self):
        if self.attached:
            return

        model.SoC.attach(self)

        for s in self.children_of_class(Cortex):
            s.attach()

    def detach(self):
        # Actually detach even if not attached, but do not complain if it hangs
        if not self.attached:
            for s in self.children_of_class(Cortex):
                try:
                    s.detach()
                except:
                    pass
            return

        for s in self.children_of_class(Cortex):
            s.detach()

        model.SoC.detach(self)

    def ram_size_probe(self, address, size):
        import random

        begin = 0
        end = size

        while end - begin >= 1024:
            token = random.randint(0, 1<<32)
            target = ((begin + end) // 2) & ~0x3ff
            try:
                cmd = [self.buses[0].cmd_u32_write(address + target, token),
                       self.buses[0].cmd_u32_read(address + target)]
                self.buses[0].execute(cmd)
                rb = cmd[-1].data
            except Exception as e:
                rb = ~token

            if rb == token:
                begin = target + 1024
            else:
                end = target

        return begin

    def trace_enable(self, width, clkdiv, formatted):
        cpu, = self.children_of_class(Cortex)
        if not cpu.tpiu or not cpu.etm:
            raise NotSupportedError("Incapable hardware")

        cpu.tpiu.stop()
        cpu.tpiu.output_mode_set(width, clkdiv, formatted)
        cpu.dwt.trace_enable()
        cpu.itm.trace_enable(1)
        cpu.etm.trace_enable(2)

    def run_attached(self):
        cpu, = self.children_of_class(Cortex)
        cpu.halt()
        cpu.reset(False)
        cpu.resume()

    def reset(self):
        cpu, = self.children_of_class(Cortex)
        cpu.reset(False)

    def write(self, program,
              do_erase = False,
              do_verify = False,
              do_start = False,
              update = True,
              assume_clean = False):
        flashs = list(self.children_of_class(StubFlash))
        if not flashs:
            return memory.Loadable.write(self, program, do_erase, do_verify, do_start, assume_clean)

        self.program_begin(do_erase, assume_clean)

        cpu, = self.children_of_class(Cortex)
        cpu.halt()

        others = [r for r in self.children_of_class(memory.Region) if r not in flashs]

        puppet = self.puppet()

        if not do_erase and update:
            with self.logger.progress("Updating", len(flashs)) as flash_progress:
                for f in flash_progress.iterate(flashs):
                    mp = program\
                         .within(f.address, f.address + f.size)\
                         .paged(f.page_size, fill = b'\xff')

                    pages = {}
                    for p in mp:
                        pages[p.address] = p.data

                    f.puppet_update(puppet, pages)
        else:
            with self.logger.progress("Flashing", len(flashs)) as flash_progress:
                for f in flash_progress.iterate(flashs):
                    blank = f.is_blank

                    mp = program\
                         .within(f.address, f.address + f.size)\
                         .paged(f.page_size, fill = b'\xff')

                    if not blank:
                        f.erase(mp.address - f.address, mp.end - mp.address)

                    pages = {}
                    for p in mp:
                        pages[p.address] = p.data

                    f.puppet_write(puppet, pages)

        with self.logger.progress("Writing", len(others)) as other_progress:
            for r in other_progress.iterate(others):
                if isinstance(r, memory.Ram):
                    continue
                blank = r.is_blank

                pages = program.within(r.address, r.address + r.size)
                if not blank:
                    r.erase(pages.address - r.address, pages.end - pages.address)

                with self.logger.progress("Writing %-8s" % r.name, len(pages)) as pprogress:
                    for p in pprogress.iterate(pages):
                        r.write(p.address - r.address, p.data)

        success = True
        if do_verify:
            success = self.verify(program)

        self.program_end(success, do_start)

@SoC.db.register_default
def default_soc(ap):
    rom_tables = ap.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        name = "Unknown SoC 0x%04x v%d from %s (0x%08x)" % (partid.part_no, partid.revision,
                                                              partid.manufacturer_name, int(partid))
        return SoC(name, ap)

    raise NotImplementedError()

@target_model.Target.register(SwDp, JtagDp)
def arm_soc_probe(dp):
    if dp.target_id:
        try:
            return SoC.db.call(dp.target_id, dp, allow_default = False)
        except (NoMatch, InitializationFailure):
            pass

    rom_tables = dp.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        return SoC.db.call(partid, dp)

    return SoC.db.call(dp.idcode, dp, allow_default = True)

    raise NotImplementedError()
