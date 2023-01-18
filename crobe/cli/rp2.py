from . import base
import click

@base.cli.group(help = "Loadable manipulation")
def rp2():
    pass

@rp2.command(help = "Dump binary info")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option("--root", "-r", type = base.ROOT, default = [], multiple = True)
def bi_dump(programs, root):
    from ..loadable.rp2 import binary_info

    for program in programs:
        print(f"From file {program.sources[0]}:")
        try:
            marker = binary_info.Marker(program)
        except ValueError:
            print(f"No RP2 binary info marker in {program.sources[0]}")
            continue

        for b in marker:
            print(b)

    for r in root:
        print(f"On device {r}:")
        try:
            marker = binary_info.Marker(r)
        except ValueError:
            print(f"No RP2 binary info marker in {r}")
            raise

        for b in marker:
            print(b)
