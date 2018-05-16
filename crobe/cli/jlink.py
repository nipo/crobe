from . import base
import click

@base.cli.group(help = "JLink-specific")
def jlink():
    pass

@jlink.command(help = "Nickname setter")
@base.roots()
@click.argument("nickname", type = str)
def nickname(roots, nickname):
    jlink = roots[0]

    from ..adapter.jlink import Adapter

    assert isinstance(jlink, Adapter)

    for i in ["swd", "jtag"]:
        try:
            interface = jlink.open(i)
        except NotImplementedError:
            continue

        interface.handle.nickname = nickname
        return
