from ... import model as target_model
from ....part_id import PartId
from .soc import SoC, BusRam, BusFlash
from ....component.arm.jtag_dp import JtagDpTap
from ....component.ti.icepick import IcePick

names = {
    PartId(0, 0x17, 0xb99a): "CC2650",
    PartId(0, 0x17, 0xb9be): "CC1310",
    }

class Cc26xx(SoC):
    def __init__(self, name, dap):
        SoC.__init__(self, name, dap)

        self.child_add(BusRam("ram", 0x20000000, 20 * 1024, self.buses[0]))
        self.child_add(BusFlash("code", 0, 128 * 1024, 4 * 1024, self.buses[0]))

@target_model.Target.register(JtagDpTap, precedence = 300)
def cc26taps_probe(tap):
    icepicks = tap.port.children_of_class(IcePick)
    for icepick in icepicks:
        if icepick.ir_pre == tap.ir_pre + tap.irlen:
            name = names.get(icepick.idcode.drop_revision(), "CC13/26xx")
            return Cc26xx(name, tap.children[0])
    raise NotImplementedError("Not my soc")
