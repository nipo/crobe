
class PartId(object):
    """
    Part Idenfifie (aka IDCode).
    """
    def __init__(self, jep106_bank, jep106_id, part_no, revision = None):
        self.jep106_bank = jep106_bank
        self.jep106_id = jep106_id
        self.part_no = part_no
        self.revision = revision

    @classmethod
    def from_idcode(cls, idcode):
        """
        Parses an IDCode (as seen in JTAG, etc.).
        """
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
        """
        Returns IDCode.
        """
        return 1 \
            | (self.jep106_id << 1) \
            | (self.jep106_bank << 8) \
            | (self.part_no << 12) \
            | ((self.revision or 0) << 28)

    def pretty(self):
        return "0x%08x (%s, 0x%04x, r%d)" % (
            int(self),
            self.manufacturer_name, self.part_no, self.revision)
    
    def is_same_part(self, other):
        """
        Compares `other` with current object, ignoring revision field.
        """
        return self.jep106_id == other.jep106_id \
            and self.jep106_bank == other.jep106_bank \
            and self.part_no == other.part_no

    def drop_revision(self):
        """
        Returns another PartId without a significant revision field.
        """
        return self.__class__(self.jep106_bank, self.jep106_id, self.part_no)
    
    def __hash__(self):
        return hash((self.jep106_bank, self.jep106_id, self.part_no, self.revision))
    
    def __eq__(self, other):
        if not isinstance(other, PartId):
            return False

        if self.revision is None or other.revision is None:
            return self.is_same_part(other)

        return self.is_same_part(other) and self.revision == other.revision

    @property
    def manufacturer_name(self):
        """
        Retrieve manufacturer name from JEP106 database.
        """
        from . import jep106
        return jep106.name_get(self.jep106_bank, self.jep106_id)
