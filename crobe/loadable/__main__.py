import click
from ..cli import base
from .object import Program
import struct

@click.group()
def cli():
    pass

@cli.command(help = "Dump file parsing results")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
def dump(program):
    Program.from_files(program).simplified().pprint()

@cli.command(help = "Convert to binary")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
@click.argument("bin", type = click.File("wb"))
def to_bin(program, bin):
    Program.from_files(program).bin_dump(bin)

@cli.command(help = "Convert to FX2 eeprom image")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
@click.argument("bin", type = click.File("wb"))
@click.option("--vid", callback = base.hex_parse, required = True, help = "Vendor ID")
@click.option("--pid", callback = base.hex_parse, required = True, help = "Product ID")
@click.option("--did", callback = base.hex_parse, required = True, help = "Device ID")
def to_fx2(program, bin, vid, pid, did):
    p = Program.from_files(program)
    bin.write(struct.pack("<BHHHB", 0xc2, vid, pid, did, 0x01))
    for s in p.simplified():
        bin.write(struct.pack(">HH", len(s), s.address))
        bin.write(s.data)
    bin.write(b'\x80\x01\xe6\x00\x00')

if __name__ == "__main__":
    cli.main()
