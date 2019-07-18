from . import base
import click

@base.cli.group(help = "JLink-specific")
def jlink():
    pass

@jlink.command(help = "Nickname setter")
@click.option('-r', '--root', type = base.ROOT)
@click.argument("nickname", type = str)
def nickname(root, nickname):
    jlink = root

    print(jlink, type(jlink))

    from ..adapter.jlink import Adapter

    assert isinstance(jlink, Adapter)

    for i in ["swd", "jtag"]:
        try:
            interface = jlink.open(i)
        except NotImplementedError:
            continue

        interface.handle.nickname = nickname
        return
