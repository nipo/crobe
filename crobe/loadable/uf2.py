from . import model
import struct

@model.Program.ext_db.register("uf2")
@model.Program.format_db.register("uf2")
class Uf2Program(model.Program):
    NOT_MAIN_FLASH = 0x00000001
    FILE_CONTAINER = 0x00001000
    FAMILY_ID      = 0x00002000
    MD5_PRESENT    = 0x00004000
    EXT_PRESENT    = 0x00008000

    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        family_id = None
        file_size = None
        block_count = None

        data_blocks = {}
        
        with open(filename, 'rb') as fd:
            while True:
                block = fd.read(512)
                if len(block) < 512:
                    break

                magic, magic2, flags, address, data_len, seq_no, total_no, fz_fam \
                    = struct.unpack("<LLLLLLLL", block[:32])
                magic_end, = struct.unpack("<L", block[-4:])

                if magic != 0x0A324655 \
                   or magic2 != 0x9E5D5157 \
                   or magic_end != 0x0AB16F30:
                    continue

                if flags & self.FAMILY_ID:
                    family_id = fz_fam

                if flags & self.FILE_CONTAINER:
                    pass
                elif not (flags & self.NOT_MAIN_FLASH):
                    data_blocks[seq_no] = address, block[32:32+data_len]

                if flags & self.EXT_PRESENT:
                    tag_data = block[32+data_len:-4]
                    while tag_data and tag_data[0]:
                        size = tag_data[0]
                        type = int.from_bytes(tag_data[1:4], "little")
                        tag = tag_data[4:size]
                        size += (-size) % 4
                        tag_data = tag_data[:size]

                        if type == 0x9fc7bc:
                            self.info["version"] = tag
                        elif type == 0x650d9d:
                            self.info["device_description"] = tag
                        elif type == 0x0be9f7:
                            self.info["page_size"] = int.from_bytes(tag[:4], "little")
                        elif type == 0xb46db0:
                            self.info["sha2"] = tag
                        elif type == 0xc8a729:
                            self.info["device_type"] = tag
                        else:
                            self.info[f"tag_{type:06x}"] = tag

            if set(data_blocks.keys()) != set(range(len(data_blocks))):
                raise ValueError("Bad data in blocks")

            p = model.Program()
            for address, data in data_blocks.values():
                p.append(model.Segment(address, data))
            for s in p.simplified():
                self.append(model.Segment(s.address + offset, s.data))
                
                        
                
