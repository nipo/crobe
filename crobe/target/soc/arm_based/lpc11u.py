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
        
@SoC.db.register(*chip_names.keys())
def lcp(dp):
    return SoC(chip_names[part_id], dp)

# class Lpc11u(model.TargetProber):
#     rom_ids = [PartId(4, 0x3b, 0x471, 0)]
#     part_ids = 
# 
#     def probe(self, target):
#         if not isinstance(target, Ap):
#             raise model.NoMatch("Not an AP")
# 
#         import struct
# 
#         target.u32_write(0xe000edf0, 0xa05f0003)
#         target.u32_write(0xe000edfc, target.u32_read(0xe000edfc) | (1 << 24))
# 
#         idcode, = struct.unpack("<L", target.mem_read(0x400483f4, 4))
#         partid = PartId.from_idcode(idcode)
# 
#         for pid, name in self.part_ids.items():
#             if partid.is_same_part(pid):
#                 return SoCTarget(name, target)
# 
#         raise model.NoMatch("Not a LCP part number")
