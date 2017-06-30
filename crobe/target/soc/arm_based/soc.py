from ... import model as target_model
from .. import model
from ....part_id import PartId
from ....component.arm.coresight.rom_table import RomTable
from ....component.arm.coresight.scs import Scs
from ....component.arm.cortex import Cortex
from ....component.arm.sw_dp import SwDp
from ....component.arm.jtag_dp import JtagDp
from ....component.arm.mem_ap import MemAp
from ....memory.region import Ram
from ....puppet import Puppet
from ....db import Db

__all__ = ["SoC", 'ArmMPuppet']

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
        ram = soc.children_of_class(Ram)[0]

        Puppet.__init__(self, cpu, ram,
                        pc_reg = cpu.registers[15],
                        sp_reg = cpu.registers[13],
                        arg_regs = cpu.registers[:4],
                        trampoline_code = b'\x01L\xa0\x47\xbe\xbe\xbe\xbe',
        )

    def stub(self, code):
        return PuppetStub(self, code)

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
