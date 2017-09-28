from ... import model as target_model
from .. import model
from ....part_id import PartId
from ....component.arm.coresight.rom_table import RomTable
from ....component.arm.coresight.scs import Scs
from ....component.arm.cortex import Cortex
from ....component.arm.sw_dp import SwDp
from ....component.arm.jtag_dp import JtagDp
from ....component.arm.mem_ap import MemAp
from ....component.nordic.ctrl_ap import CtrlAp
from ... import memory
from ....puppet import Puppet
from ....db import Db
from ....util.info import TimedLogger

__all__ = ["SoC", 'ArmMPuppet', 'StubFlash']

class PuppetStub:
    def __init__(self, puppet, code):
        self.puppet = puppet
        self.code = code
        self.zone = self.puppet.allocate(len(code))

    def call(self, *args):
        self.zone.write(self.code)
        return self.puppet.call(self.zone.address + 1, *args)

    def prepare(self, *args):
        self.zone.write(self.code)
        return self.puppet.prepare(self.zone.address + 1, *args)

    def run(self):
        return self.puppet.run()

    def wait(self):
        self.puppet.wait()
        r0 = self.puppet.arg_regs[0]
        return self.puppet.cpu.reg_read([r0])[r0]

    def __del__(self):
        self.puppet.unallocate(self.zone)
    
class ArmMPuppet(Puppet):
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
        self.bus.mem_write(self.address + offset, size)

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
        self.__prepared = False

    def _prepare(self):
        if self.__prepared:
            return
        self.prepare()
        self.__prepared = True

    def prepare(self):
        pass

    def erase(self, offset, size):
        self.prepare()

        with TimedLogger(self.logger,
                         "erase 0x%08x-0x%08x" % (
            self.address + offset, self.address + offset + size)):
            puppet = self.soc.puppet()
            code = puppet.stub(self.RANGE_ERASE)
            code.call(self.address + offset, size, self.page_size)

        if size == self.size:
            self.is_blank = True
            
    def write(self, offset, data):
        assert offset % self.page_size == 0

        with TimedLogger(self.logger,
                         "write 0x%08x-0x%08x" % (
            self.address + offset, self.address + offset + len(data))):
            puppet = self.soc.puppet()
            code = puppet.stub(self.PAGE_WRITE)

            page_zone = puppet.allocate(self.page_size, self.page_size)
            for off in range(0, len(data), self.page_size):
                chunk = data[off : off + self.page_size]
                page_zone.write(chunk)
                code.call(self.address + off, page_zone.address, len(chunk))
            puppet.unallocate(page_zone)

        self.force_blank(False)

    def load(self, program):
        self.prepare()

        puppet = self.soc.puppet()
        code = puppet.stub(self.PAGE_WRITE)

        if True:
            page_zone = puppet.allocate(self.page_size, self.page_size), \
                        puppet.allocate(self.page_size, self.page_size)

            running = None
            for i, page in enumerate(program.paged(self.page_size, fill = b'\xff')):
                self.logger.info("Loading page at 0x%08x...", page.address)
                z = page_zone[i % 2]

                z.write(page.data)

                if running is not None:
                    self.logger.info("Done writing page at 0x%08x...", running)
                    code.wait()
                    running = None

                code.prepare(page.address, z.address, self.page_size)
                code.run()
                running = page.address

            if running:
                code.wait()
                self.logger.info("Done writing page at 0x%08x...", running)
            puppet.unallocate(page_zone[0])
            puppet.unallocate(page_zone[1])
        else:
            page_zone = puppet.allocate(self.page_size, self.page_size)
            for i, page in enumerate(program.paged(self.page_size, fill = b'\xff')):
                self.logger.info("Loading page at 0x%08x...", page.address)
                chunk = 256
                for i in range(0, self.page_size, chunk):
                    page_zone.write(page.data[i:i+chunk], i)
                code.call(page.address, page_zone.address, self.page_size)
                self.logger.info("Done writing page at 0x%08x", page.address)
            puppet.unallocate(page_zone)

class SoC(model.SoC):
    db = Db()

    def __init__(self, name, port):
        model.SoC.__init__(self, name)
        self.port = port
        self.buses = port.children_of_class(MemAp)
        
        idx = 0
        for mem_ap in self.buses:
            for s in mem_ap.children_of_class(Scs):
                rt, = port.children_find(lambda x: isinstance(x, RomTable) and s in x.children)
                self.child_add(Cortex.from_romtable(rt, idx))
                idx += 1

    def puppet(self):
        return ArmMPuppet(self)

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
        except:
            pass

    rom_tables = dp.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        return SoC.db.call(partid, dp)

    raise NotImplementedError()
