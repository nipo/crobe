from ...util.endian import bitswap8
from ... import bitstring
from . import opcodes

class Frame:
    def __init__(self, data, crc = None):
        self.data = data
        self.crc = crc

class BsReader:
    def __init__(self, blob):
        self.blob = blob
        self.point = 0
        self.bit_buffer = bitstring.BitString()

    def get(self, count):
        self.bit_buffer = bitstring.BitString()
        if not count:
            return b''
        r = self.blob[self.point : self.point + count]
        self.point += count
        if self.point > len(self.blob):
            raise ValueError("Read overflow")
        return r

    def big_get(self, count):
        return int.from_bytes(self.get(count), "big")

    def inc_get(self, count, crc, padding, frame_bit_size):
        frame_byte_size = (frame_bit_size + 7) // 8
        ret = []
        c = None
        for i in range(count):
            data = self.get(frame_byte_size)
            if crc:
                c = self.big_get(2)
            ret.append(Frame(data, c))
            padding = self.get(padding)
        return ret

    def bits_get(self, count):
        bb = self.bit_buffer
        bytes_to_read = (count - len(bb) + 7) // 8
        blob = self.get(bytes_to_read)
        blob = blob[::-1]
        bba = bitstring.BitString(blob)
        bb = bba + bb
        rb = bb[len(bb)-count:len(bb)]
        r = int(rb)
        self.bit_buffer = bb[0:len(bb)-count]
        return r

    def __bool__(self):
        return self.point != len(self.blob)

class Bitstream:
    HEADER = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])

    def __init__(self, parts, prog):
        data = prog.segment_at(0).data
        if data.startswith(bitswap8(self.HEADER)):
            data = bitswap8(data)

        reader = BsReader(data)

        if reader.get(len(self.HEADER)) != self.HEADER:
            raise ValueError("Bitstream data does not start with expected header")

        self.rti = []
        self.ebr = {}
        self.usercode = 0
        self.info = None
        ebr_addr = 0

        if "Part" in prog.info:
            part = "-".join(prog.info["Part"].split("-")[:2])
            self.info = [p for p in parts if p.name == part][0]
            assert self.info.col_bit_count == int(prog.info["Cols"])
            assert self.info.row_count == int(prog.info["Rows"])

        elif "device" in prog.info:
            part = "-".join(prog.info["device"].split("-")[:2])
            self.info = [p for p in parts if p.name == part][0]

        comp_dict = b'\x00' * 8
        
        while reader:
            cmd = reader.big_get(1)
            
            if cmd in [0xff, 0]:
                continue

            #print(hex(cmd))

            args = reader.big_get(3)
        
            if cmd == opcodes.LSC_RESET_CRC:
                pass

            elif cmd == opcodes.VERIFY_ID:
                idcode = reader.big_get(4)
                if self.info:
                    assert idcode == self.info.idcode
                else:
                    self.info = [p for p in parts if p.idcode == idcode][0]

            elif cmd == opcodes.LSC_WRITE_COMP_DIC:
                comp_dict = reader.get(8)[::-1]

            elif cmd in [opcodes.LSC_PROG_CTRL0, opcodes.LSC_READ_CTRL0]:
                reader.get(4)

            elif cmd == opcodes.LSC_INIT_ADDRESS:
                addr = 0

            elif cmd == opcodes.LSC_PROG_INCR_RTI:
                do_crc_comp = bool(args & 0x800000)
                do_crc_at_end = bool(args & 0x400000)
                has_dummy_bits = bool(args & 0x200000)
                has_dummy_bit_count = bool(args & 0x100000)
                dummy_bit_count = (args & 0x0f0000) >> 16
                frame_count = args & 0xffff

                padding = 0 if has_dummy_bits else (has_dummy_bit_count if has_dummy_bit_count else 1)

                assert frame_count == self.info.row_count

                rows = reader.inc_get(args & 0xffff, not (args & 0x400000), padding, self.info.col_bit_count)
                self.rti = rows

            elif cmd == opcodes.LSC_PROG_INCR_CMP:
                do_crc_comp = bool(args & 0x800000)
                do_crc_at_end = bool(args & 0x400000)
                has_dummy_bits = bool(args & 0x200000)
                has_dummy_bit_count = bool(args & 0x100000)
                dummy_bit_count = (args & 0x0f0000) >> 16
                frame_count = args & 0xffff
                assert frame_count == self.info.row_count

                flen = self.info.col_bit_count//8
                rows = []
                
                for fno in range(frame_count):
                    frame = b''
                    while len(frame) < ((flen + 7) & ~7):
                        if reader.bits_get(1) == 0:
                            #print(fno, len(frame), "z")
                            frame += b'\x00'
                        elif reader.bits_get(1) == 1:
                            b = reader.bits_get(8)
                            #print(fno, len(frame), "v", hex(b))
                            frame += bytes([b])
                        elif reader.bits_get(1) == 1:
                            idx = reader.bits_get(3)
                            #print(fno, len(frame), "c", idx, hex(comp_dict[idx]), comp_dict.hex())
                            frame += comp_dict[idx:idx+1]
                        else:
                            idx = reader.bits_get(3)
                            #print(fno, len(frame), "1", idx, hex(1 << idx))
                            frame += bytes([1 << idx])
                    frame = frame[-flen:]
                    crc = None
                    reader.get(0)
                    if not do_crc_at_end:
                        crc = reader.big_get(2)
                    rows.append(Frame(frame, crc))
                    
                self.rti = rows

            elif cmd == opcodes.LSC_PROG_SED_CRC:
                reader.get(4)

            elif cmd == opcodes.ISC_PROGRAM_SECURITY:
                pass

            elif cmd == opcodes.ISC_PROGRAM_USERCODE:
                self.usercode = reader.big_get(4)

            elif cmd == opcodes.LSC_WRITE_BUS_ADDRESS:
                ebr_addr = reader.big_get(4)

            elif cmd == opcodes.LSC_EBR_WRITE:
                padding = 0 if (args & 0x200000) else (((args >> 16) & 0xf) if args & 0x100000 else 1)

                rows = reader.inc_get(args & 0xffff, bool(args & 0x400000), padding, 72)
                self.ebr[ebr_addr] = rows

            elif cmd == opcodes.ISC_PROGRAM_DONE:
                pass

            elif cmd == opcodes.LSC_PCS_WRITE:
                reader.big_get(args & 0xff)

            else:
                raise ValueError("UNKNOWN: %02x" % cmd, hex(reader.point))
        
            if args & 0x800000:
                reader.big_get(2)

    @property
    def data(self):
        return b''.join(f.data for f in self.rti)

if __name__ == '__main__':
    import sys
    from . import parts
    from ...loadable.object import Program
    bs = Bitstream(parts.PARTS, Program.from_file(sys.argv[1]))
    open(sys.argv[2], "wb").write(bs.data)
