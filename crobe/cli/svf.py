from . import base
import click
from ..component.xilinx import zynq
import binascii

@base.cli.group(help = "Serial Vector Format")
def svf():
    pass

@svf.command(help = "SVF playback machine")
@click.argument("file", type = click.File("rb"))
@click.option('-r', '--root', type = base.ROOT)
def play(root, file):
    from ..svf import player
    from ..svf import svf
    from ..protocol.jtag import Interface, Chain, Tap

    svf = svf.Parser(file)

    if isinstance(root, Interface):
        root = root.children[0]

    if isinstance(root, Chain):
        player = player.ChainPlayer(root)
    elif isinstance(root, Tap):
        player = player.TapPlayer(root)
    else:
        click.echo("Root %s is not a JTAG chain nor a TAP" % root)
        return

    player.run(svf)
