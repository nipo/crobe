from . import base
from ..protocol import one_wire
import click

@base.cli.group(help = "1-Wire manipulation", name = "1wire")
def one_wire_():
    pass

@one_wire_.command(help = "Perform discovery on bus")
@click.option('-r', '--root', "root", type = base.ROOT)
def discovery(root):
    found = root.discovery()
    for f in found:
        print(f"Found {f}")

    if len(found) == 1:
        rom = root.global_command(root.READ_ROM, rsize = 8)
        read = one_wire.Rom.from_raw(rom)
        assert found[0] == read

