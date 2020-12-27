from . import base
from ..util.pretty import metric
import click

@base.cli.group(help = "Ethernet fiddling")
def ethernet():
    pass

@ethernet.command(help = "Run cable diagnostics through PHY MII")
@click.option('-r', '--root', type = base.ROOT)
def tdr(root):
    result = root.tdr_execute()
    for r in result:
        print(r)
