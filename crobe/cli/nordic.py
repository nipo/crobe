from . import base
import click
from ..component.nordic import ctrl_ap
import binascii
import time

@base.cli.group(help = "Nordic-specific")
def nordic():
    pass

@nordic.command(help = "Erase using Ctrl-AP")
@click.option('-r', '--root', type = base.ROOT)
def erase(root):
    try:
        ap, = root.children_of_class(ctrl_ap.CtrlAp, include_self = True)
    except ValueError:
        raise ValueError("Root does not have exactly one Ctrl AP in subtree")
    click.echo("Target: %s" % ap)

    ap.erase_all()
    ap.reset = True
    time.sleep(.1)
    ap.reset = False

@nordic.command(help = "Reset target using Ctrl-AP")
@click.option('-r', '--root', type = base.ROOT)
def reset(root):
    try:
        ap, = root.children_of_class(ctrl_ap.CtrlAp, include_self = True)
    except ValueError:
        raise ValueError("Root does not have exactly one Ctrl AP in subtree")
    click.echo("Target: %s" % ap)

    ap.reset = True
    ap.reset = False
