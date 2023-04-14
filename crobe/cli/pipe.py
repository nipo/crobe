from . import base
import click

@base.cli.group(help = "Pipes")
def pipe():
    pass

@pipe.command(help = "Dump pipe to terminal")
@click.option("--root", "-r", type = base.ROOT)
def dump(root):
    while True:
        data = root.read(1024, timeout = .1)
        data = str(data, 'ascii', 'ignore')
        print(data, end = '', flush = True)
