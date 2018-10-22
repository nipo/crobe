from ...util.endian import bitswap8

class Frame:
    def __init__(self, data, crc = None):
        self.data = data
        self.crc = crc

class BsReader:
    def __init__(self, blob):
        self.blob = blob
        self.point = 0

    def get(self, count):
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
            data = bitswap8(self.get(frame_byte_size))
            if crc:
                c = self.big_get(2)
            ret.append(Frame(data, c))
            padding = self.get(padding)
        return ret

    def __bool__(self):
        return self.point != len(self.blob)

class MachXOBitstream:
    HEADER = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])

    def __init__(self, parts, prog):
        reader = BsReader(prog.segment_at(0).data)

        if "Part" not in prog.info:
            raise ValueError("Can only parse bitstream with ASCII header")

        if reader.get(len(self.HEADER)) != self.HEADER:
            raise ValueError("Bitstream data does not start with expected header")

        part = "-".join(prog.info["Part"].split("-")[:2])
        
        self.info = [p for p in parts if p.name == part][0]
        self.rti = []
        self.ebr = {}
        self.usercode = 0
        ebr_addr = 0

        assert self.info.col_bit_count == int(prog.info["Cols"])
        assert self.info.row_count == int(prog.info["Rows"])
        
        while reader:
            cmd = reader.big_get(1)
        
            if cmd == 0xff:
                continue

            args = reader.big_get(3)
        
            if cmd == MachXO2.IR_LSC_RESET_CRC:
                pass

            elif cmd == MachXO2.IR_VERIFY_ID:
                idcode = reader.big_get(4)
                assert idcode == self.info.idcode

            elif cmd == MachXO2.IR_LSC_WRITE_COMP_DIC:
                raise NotImplementedError("Compressed bitstream support not implemented")
                reader.get(8)

            elif cmd == MachXO2.IR_LSC_PROG_CTRL0:
                reader.get(4)

            elif cmd == MachXO2.IR_LSC_INIT_ADDRESS:
                addr = 0

            elif cmd == MachXO2.IR_LSC_PROG_INCR_RTI:
                padding = 0 if (args & 0x200000) else (((args >> 16) & 0xf) if args & 0x100000 else 1)

                rows = reader.inc_get(args & 0xffff, not (args & 0x400000), padding, self.info.col_bit_count)
                self.rti = rows

            elif cmd == MachXO2.IR_LSC_PROG_INCR_CMP:
                raise NotImplementedError("Compressed bitstream support not implemented")
                reader.get(8)

            elif cmd == MachXO2.IR_LSC_PROG_SED_CRC:
                reader.get(4)

            elif cmd == MachXO2.IR_ISC_PROGRAM_SECURITY:
                pass

            elif cmd == MachXO2.IR_ISC_PROGRAM_USERCODE:
                self.usercode = reader.big_get(4)

            elif cmd == MachXO2.IR_LSC_WRITE_BUS_ADDRESS:
                ebr_addr = reader.big_get(4)

            elif cmd == MachXO2.IR_LSC_EBR_WRITE:
                padding = 0 if (args & 0x200000) else (((args >> 16) & 0xf) if args & 0x100000 else 1)

                rows = reader.inc_get(args & 0xffff, bool(args & 0x400000), padding, 72)
                self.ebr[ebr_addr] = rows

            elif cmd == MachXO2.IR_ISC_PROGRAM_DONE:
                pass

            elif cmd == MachXO2.IR_LSC_PCS_WRITE:
                reader.big_get(args & 0xff)

            else:
                raise ValueError("UNKNOWN: %02x" % cmd, point)
        
            if args & 0x800000:
                reader.big_get(2)
