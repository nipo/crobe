from .soc import SoC
from ....part_id import PartId

chip_names = {
    PartId(0, 0x15, 0x95C8): "LPC11U12",
    PartId(0, 0x15, 0x97A8): "LPC11U13",
    PartId(0, 0x15, 0x9988): "LPC11U14",
    PartId(0, 0x15, 0x9544): "LPC11U22",
    PartId(0, 0x15, 0x9724): "LPC11U23",
    PartId(0, 0x15, 0x9884): "LPC11U24",
    PartId(0, 0x15, 0x9800): "LPC11U24",
}

class Lpc11u(SoC):
    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)

@SoC.db.register(PartId(4, 0x3b, 0x471))
def lcp_ducktyping(dp):
    from ....component.arm.mem_ap import MemAp

    try:
        ap, = dp.children_find(lambda x: isinstance(x, MemAp))
        idcode = ap.u32_read(0x400483f4)

        # Clear out revision field
        partid = PartId.from_idcode(idcode).drop_revision()

        if partid in chip_names:
            return Lpc11u(chip_names[partid], dp)
    except:
        pass

    raise NotImplementedError("Not a known LPC idcode" % partid)
