from ... import model as target_model
from .. import model
from ....part_id import PartId
from ....component.arm.coresight.rom_table import RomTable
from ....component.arm.coresight.scs import Scs
from ....component.arm.coresight.dwt import Dwt
from ....component.arm.coresight.fpb import Fpb
from ....component.arm import cortex
from ....component.arm.dap import SwDp, JtagDp
from ....component.arm.mem_ap import MemAp
from ....db import Db

__all__ = ["SoC"]

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
                self.child_add(self.cpu_for_romtable(idx, rt))
                idx += 1

    def cpu_for_romtable(self, index, rt):
        scs, = rt.children_of_class(Scs)

        try:
            fpb, = rt.children_of_class(Fpb)
        except:
            fpb = None

        try:
            dwt, = rt.children_of_class(Dwt)
        except:
            dwt = None

        return cortex.cpu_for(index, scs, fpb, dwt)
            
@SoC.db.register_default
def default_soc(ap):
    rom_tables = ap.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        name = "Unknown SoC 0x%04x v%d from %s (0x%08x)" % (partid.part_no, partid.revision,
                                                              partid.manufacturer_name, int(partid))
        return SoC(name, ap)

    raise NotImplementedError()

@target_model.Target.register(SwDp)
def arm_soc_probe(ap):
    rom_tables = ap.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        return SoC.db.call(partid, ap)

    raise NotImplementedError()

@target_model.Target.register(JtagDp)
def arm_soc_probe(ap):
    rom_tables = ap.children_of_class(RomTable)
    if rom_tables:
        partid = rom_tables[0].partid

        return SoC.db.call(partid, ap)

    raise NotImplementedError()
