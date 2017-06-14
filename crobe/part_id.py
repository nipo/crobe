
class PartId(object):
    def __init__(self, jep106_bank, jep106_id, part_no, revision = None):
        self.jep106_bank = jep106_bank
        self.jep106_id = jep106_id
        self.part_no = part_no
        self.revision = revision

    @classmethod
    def from_idcode(cls, idcode):
        if not (idcode & 1):
            raise ValueError("LSB of IDCODE must be 1")

        return cls((idcode >> 8) & 0xf, (idcode >> 1) & 0x7f,
                      (idcode >> 12) & 0xffff, (idcode >> 28) & 0xf)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        if self.revision is not None:
            return "%s(%d, 0x%x, 0x%x, %d)" % (self.__class__.__name__, self.jep106_bank, self.jep106_id, self.part_no, self.revision)
        return "%s(%d, 0x%x, 0x%x)" % (self.__class__.__name__, self.jep106_bank, self.jep106_id, self.part_no)
    
    def __int__(self):
        return 1 \
            | (self.jep106_id << 1) \
            | (self.jep106_bank << 8) \
            | (self.part_no << 12) \
            | ((self.revision or 0) << 28)
    
    def is_same_part(self, other):
        return self.jep106_id == other.jep106_id \
            and self.jep106_bank == other.jep106_bank \
            and self.part_no == other.part_no

    def drop_revision(self):
        return self.__class__(self.jep106_bank, self.jep106_id, self.part_no)
    
    def __hash__(self):
        return hash((self.jep106_bank, self.jep106_id, self.part_no, self.revision))
    
    def __eq__(self, other):
        if self.revision is None or other.revision is None:
            return self.is_same_part(other)

        return self.is_same_part(other) and self.revision == other.revision

    @property
    def manufacturer_name(self):
        from . import jep106
        return jep106.name_get(self.jep106_bank, self.jep106_id)
