from . import base
import click

@base.cli.group(help = "Loadable manipulation")
def rp2():
    pass

@rp2.command(help = "Dump binary info")
@click.argument("program", type = base.PROGRAM)
def bi_dump(program):
    from ..loadable.rp2 import binary_info
    try:
        marker = binary_info.Marker(program)
    except ValueError:
        print(f"No RP2 binary info marker in {program.filename}")

    for b in marker:
        print(b)
