from .soc import SoC
from ....part_id import PartId

chip_names = {
    PartId(0, 0x15, 0x95C8, 0): "LPC11U12",
    PartId(0, 0x15, 0x97A8, 0): "LPC11U13",
    PartId(0, 0x15, 0x9988, 0): "LPC11U14",
    PartId(0, 0x15, 0x9544, 0): "LPC11U22",
    PartId(0, 0x15, 0x9724, 0): "LPC11U23",
    PartId(0, 0x15, 0x9884, 0): "LPC11U24",
    PartId(0, 0x15, 0x9800, 0): "LPC11U24",
}

@SoC.db.register(PartId(4, 0x3b, 0x471, 0))
def lcp_ducktyping(dp):
    from ....arm.mem_ap import MemAp
    ap, = dp.children_find(lambda x: isinstance(x, MemAp))
    idcode = ap.u32_read(0x400483f4)
    # Clear out revision field
    partid = PartId.from_idcode(idcode & 0x0fffffff)
    if partid in chip_names:
        return SoC(chip_names[partid], dp)
    raise KeyError(partid)
