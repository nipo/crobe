import click
from .object import Program

@click.group()
def cli():
    pass

@cli.command(help = "Dump file parsing results")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
def dump(program):
    Program.from_files(program).pprint()

@cli.command(help = "Convert to binary")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
@click.argument("bin", type = click.File("wb"))
def to_bin(program, bin):
    Program.from_files(program).bin_dump(bin)

if __name__ == "__main__":
    cli.main()
