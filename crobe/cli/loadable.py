from . import base
from ..util import endian
import click
import click
from ..loadable.object import Program
import struct

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
    Program.from_programs(programs).simplified().pprint()
        
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

if __name__ == "__main__":
    cli.main()
