import collections

class PartId(collections.namedtuple("IdCode", ["jep106_bank", "jep106_id", "part_no", "revision"])):
    @classmethod
    def from_idcode(cls, idcode):
        if not (idcode & 1):
            raise ValueError("LSB of IDCODE must be 1")
        return cls((idcode >> 8) & 0xf, (idcode >> 1) & 0x7f,
                      (idcode >> 12) & 0xffff, (idcode >> 28) & 0xf)

    def __int__(self):
        return 1 \
            | (self.jep106_id << 1) \
            | (self.jep106_bank << 8) \
            | (self.part_no << 12) \
            | (self.revision << 28)

    def is_same_part(self, other):
        return self.jep106_id == other.jep106_id \
            and self.jep106_bank == other.jep106_bank \
            and self.part_no == other.part_no

    @property
    def manufacturer_name(self):
        from . import jep106
        return jep106.name_get(self.jep106_bank, self.jep106_id)
