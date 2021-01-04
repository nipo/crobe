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

    from ..adapter.jlink import JLink

    assert isinstance(jlink, JLink)

    handle = jlink.handle_get()
    handle.nickname = nickname

@jlink.command(help = "Firmware dumper")
@click.option('-r', '--root', type = base.ROOT)
@click.option('-a', '--address', type = base.HEX)
@click.option('-s', '--size', type = base.HEX)
@click.option('-f', '--file', type = str)
def fw_dump(root, address, size, file):
    jlink = root

    print(jlink, type(jlink))

    from ..adapter.jlink import JLink
    from ..adapter.jlink import backend

    assert isinstance(jlink, JLink)

    handle = jlink.handle_get()
    licenses = backend.GetLicenses()
    config = backend.ReadConfig()
    handle.execute([licenses, config])
    print(f"Serial: {licenses.serial}")
    print(f"Licenses: {', '.join(licenses.licenses)}")
    print(f"Config: {config.data.hex()}")

    data = handle.firmware_read(address, size)
    from ..loadable.object import Program, Segment
    p = Program()
    p.append(Segment(address, data))
    p.save_hex(file)
