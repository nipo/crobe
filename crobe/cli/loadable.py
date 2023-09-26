from . import base
from ..util import endian
import click
import click
from ..loadable.object import Program
import struct
import re

def program_get(programs, within):
    p = Program.from_programs(programs)
    if not within:
        return p
    
    rp = Program()
    for begin, end in within:
        rp += p.within(begin, end)
    return rp

@base.cli.group(help = "Loadable manipulation")
def loadable():
    pass

@loadable.command(help = "Dump file parsing results")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
def dump(programs):
    Program.from_programs(programs).pprint()
        
@loadable.command(help = "Convert to binary")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.argument("bin", type = click.File("wb"))
@click.option('-s', '--bitswap', is_flag = True, help = "Byte swap output")
@click.option("--within", type = base.ADDRESS_RANGE, multiple = True)
def to_bin(programs, bin, within, bitswap):
    program_get(programs, within).bin_dump(bin, bitswap = bitswap)

@loadable.command(help = "Convert to hex")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.argument("hex", type = click.File("w"))
@click.option("--within", type = base.ADDRESS_RANGE, multiple = True)
@click.option("--paged", type = int, default = 0)
def to_hex(programs, hex, within, paged):
    p = program_get(programs, within)
    if paged:
        p = p.paged(paged)
    p.save_hex(hex.name)

@loadable.command(help = "Convert to FX2 eeprom image")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.argument("bin", type = click.File("wb"))
@click.option("--vid", type = base.HEX, required = True, help = "Vendor ID")
@click.option("--pid", type = base.HEX, required = True, help = "Product ID")
@click.option("--did", type = base.HEX, required = True, help = "Device ID")
def to_fx2(programs, bin, vid, pid, did):
    p = Program.from_programs(programs).simplified()
    bin.write(struct.pack("<BHHHB", 0xc2, vid, pid, did, 0x41))
    for s in p.simplified():
        bin.write(struct.pack(">HH", len(s), s.address))
        bin.write(s.data)
    bin.write(b'\x80\x01\xe6\x00\x00')

@loadable.command(help = "Convert to FX3 eeprom image")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.argument("bin", type = click.Path(dir_okay = False))
def to_fx3(programs, bin):
    p = Program.from_programs(programs)
    p.save_cypress_img(bin)

@loadable.command(help = "Convert to MEM image")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.argument("mem", type = click.File("w"))
def to_mem(programs, mem):
    p = Program.from_programs(programs).simplified()
    for s in p:
        mem.write("@%07x\n" % s.address)
        for b in s.data:
            mem.write("%02x\n" % b)

@loadable.command(help = "Hex dump image")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option("--within", type = base.ADDRESS_RANGE, multiple = True)
@click.option('-s', '--bitswap', is_flag = True, help = "Byte swap output")
def hexdump(programs, within, bitswap):
    from ..util.hexdump import hexdump
    p = program_get(programs, within)
    for s in p:
        if s.name:
            print(f"{s.name}:")
        data = s.data
        if bitswap:
            data = endian.bitswap8(data)
        hexdump(s.address, data, printer = print)

@loadable.command(help = "C blob file generator")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option("--within", type = base.ADDRESS_RANGE, multiple = True)
@click.option('-s', '--bitswap', is_flag = True, help = "Byte swap output")
@click.option('-n', '--name', type = str, default = "blob", help = "Variable name")
@click.option('--align', type = int, default = 1, help = "Alignment constraint")
@click.option('--section', type = str, default = None, help = "Target section")
@click.option('--static', is_flag = True, default = False, help = "Emit symbols as static")
@click.option('--extern', is_flag = True, default = False, help = "Only emit symbol forward declarations")
@click.option('-S', '--size', is_flag = True, default = False, help = "Also emit size constant")
@click.argument("output", type = click.File("w"))
def to_c_blob(programs, within, bitswap, output, name, align, section, size, static, extern):
    p = program_get(programs, within).simplified()
    if len(p) > 1:
        raise ValueError("Loadable has more than one segment")
    data = p[0].data
    if bitswap:
        data = endian.bitswap8(data)

    guard_name = re.sub('[^A-Z]+', '_', name.upper()) + "_DECLARED"

    if static and extern:
        raise ValueError("Cannot be extern and static at the same time")
        
    output.write(f"""\
#ifndef {guard_name}
#define {guard_name}

#include <stdint.h>
#include <stdlib.h>

""")

    if not extern:
        if section:
            output.write(f"__attribute__((section \"{section}\"))\n")
        if align != 1:
            output.write(f"__attribute__((aligned ({align})))\n")
    if static:
        output.write(f"static ")
    elif extern:
        output.write(f"extern ")
    output.write(f"const uint8_t {name}[]")
    if not extern:
        output.write(f" = {{\n")
        for off in range(0, len(data), 16):
            subset = data[off : min(len(data) , off + 16)]
            line = ', '.join(f'{v:#04x}' for v in subset)
            output.write(f" /* {off:#010x}: */ {line},\n")
        output.write(f"}}")
    output.write(f";\n")
    
    if size:
        if static:
            output.write(f"static ")
        elif extern:
            output.write(f"extern ")
        output.write(f"const size_t {name}_size")
        if not extern:
            output.write(f" = {len(data):#x}")
        output.write(f";\n\n")

    output.write(f"""\
#endif
""")

@loadable.command(help = "Do CRC of an image")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option("--alg", type = str)
@click.option("--swap4", is_flag = True)
def crc(programs, alg, swap4):
    from ..util.crc import Crc
    crc_alg = Crc.from_desc_string(alg)
    for p in programs:
        for s in p:
            ctx = crc_alg()
            data = s.data
            if swap4:
                data = b"".join(data[i:i+4][::-1] for i in range(0, len(data), 4))
            ctx.update(data)
            print(f"{p.sources[0]} {s.name} <{s.address:#x}:{s.address+len(s.data):#x}>: {bytes(ctx).hex()}")


if __name__ == "__main__":
    cli.main()
