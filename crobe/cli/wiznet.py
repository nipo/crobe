from . import base
import click

@base.cli.group(help = "Wiznet testing")
def wiznet():
    pass

@wiznet.command(help = "Try ethernet adapter")
@click.option('-r', '--root', type = base.ROOT)
def demo(root):
    w = root

    w.init()
    
