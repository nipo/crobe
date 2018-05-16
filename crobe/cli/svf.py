from . import base
import click
from ..component.xilinx import zynq
import binascii

@base.cli.group(help = "Serial Vector Format")
def svf():
    pass

@svf.command(help = "SVF playback machine")
@click.argument("file", type = click.File("rb"))
@base.roots()
def play(roots, file):
    from ..svf.player import ChainPlayer, TapPlayer
    from ..svf.svf import SvfParser
    from ..adapter.protocol.jtag import Interface, Chain, Tap

    svf = SvfParser(file)
    root = roots[0]

    if isinstance(root, Interface):
        root = root.children[0]

    if isinstance(root, Chain):
        player = ChainPlayer(root)
    elif isinstance(root, Tap):
        player = TapPlayer(root)
    else:
        click.echo("Root %s is not a JTAG chain nor a TAP" % root)
        return

    player.run(svf)
