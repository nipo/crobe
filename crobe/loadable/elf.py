from . import model

@model.Program.ext_db.register("elf")
@model.Program.ext_db.register("axf")
@model.Program.ext_db.register("out")
@model.Program.format_db.register("elf")
class ElfProgram(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        from elftools.elf.elffile import ELFFile

        self.fd = open(filename, "rb")
        self.elf = ELFFile(self.fd)

        for segno in range(self.elf.num_segments()):
            seg = self.elf.get_segment(segno)
            if seg["p_type"] != "PT_LOAD":
                continue

            sections = []
            for section in self.elf.iter_sections():
                if seg.section_in_segment(section):
                    sections.append(section.name)
            
            self.append(model.Segment(seg["p_paddr"], seg.data().ljust(seg['p_memsz'], b'\x00'), filename, name = ' '.join(sections)))

        self.info["device"] = self.elf.get_machine_arch()
        self.info["entry"] = self.elf.header["e_entry"]

    def symbol_address_get(self, name):
        symtab = self.elf.get_section_by_name('.symtab')
        if not symtab:
            return None

        symbols = symtab.get_symbol_by_name(name)
        if not symbols:
            return None

        symbol = symbols[0]

        return symbol.entry["st_value"]

    def close(self):
        self.fd.close()
