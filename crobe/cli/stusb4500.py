from . import base
import click
import yaml

@base.cli.group()
def stusb4500():
    "STUSB4500-specific"

class Stusb4500Cli:
    @staticmethod
    def config_load(path):
        with open(path) as fd:
            config = yaml.safe_load(fd)
        if not isinstance(config, dict):
            raise click.ClickException(f"{path}: expected a mapping")
        return config

    @staticmethod
    def sectors_parse(text):
        from ..component.st.stusb4500 import StUsb4500Nvm

        data = bytes.fromhex("".join(text.split()))
        if len(data) != 8 * len(StUsb4500Nvm.BANKS):
            raise click.ClickException(f"Expected {8 * len(StUsb4500Nvm.BANKS)} bytes, got {len(data)}")
        return [data[i:i+8] for i in range(0, len(data), 8)]

    @staticmethod
    def nvm_build(config, device_sectors):
        from ..component.st.stusb4500 import StUsb4500Nvm

        config = dict(config)
        base_name = config.pop("base", None)
        if base_name == "default":
            base_sectors = StUsb4500Nvm.DEFAULT
        elif base_name == "device":
            if device_sectors is None:
                raise click.ClickException("base: device needs a device")
            base_sectors = device_sectors
        else:
            raise click.ClickException("base must be either 'default' or 'device'")

        try:
            return StUsb4500Nvm.from_config(config, base_sectors)
        except ValueError as e:
            raise click.ClickException(str(e))

    @staticmethod
    def diff_print(old, new):
        old_config = old.to_config()
        new_config = new.to_config()
        for k, v in new_config.items():
            if old_config[k] != v:
                click.echo(f"{k}: {old_config[k]} -> {v}")
        for i, (o, n) in enumerate(zip(old.sectors(), new.sectors())):
            if o != n:
                click.echo(f"Sector {i}: {o.hex()} -> {n.hex()}")

@stusb4500.command()
@click.option('-r', '--root', type = base.ROOT)
@click.option('-n', '--dry-run', is_flag = True, help = "Only show changes")
@click.argument('config', type = click.Path(exists = True, dir_okay = False))
def program(root, dry_run, config):
    """Program customization from a YAML file"""

    from ..component.st.stusb4500 import StUsb4500, StUsb4500Nvm

    assert isinstance(root, StUsb4500)

    current = StUsb4500Nvm(root.customization_get())
    nvm = Stusb4500Cli.nvm_build(Stusb4500Cli.config_load(config), current.sectors())

    if nvm.sectors() == current.sectors():
        click.echo("NVM already up to date")
        return

    Stusb4500Cli.diff_print(current, nvm)
    if dry_run:
        return

    root.customization_set(nvm.sectors())
    if root.customization_get() != nvm.sectors():
        raise click.ClickException("NVM readback mismatch")
    click.echo("NVM programmed, power-cycle the device to apply")

@stusb4500.command()
@click.option('-r', '--root', type = base.ROOT)
@click.option('-o', '--output', type = click.File('w'), help = "Write YAML config")
def dump(root, output):
    """Dump customization"""

    from ..component.st.stusb4500 import StUsb4500, StUsb4500Nvm

    assert isinstance(root, StUsb4500)

    nvm = StUsb4500Nvm(root.customization_get())
    if output:
        yaml.safe_dump({"base": "device", **nvm.to_config()}, output, sort_keys = False)
    else:
        nvm.pretty(click.echo)

@stusb4500.command()
@click.argument('sectors')
@click.option('-o', '--output', type = click.File('w'), help = "Write YAML config")
def decode(sectors, output):
    """Decode customization from 40 hex bytes"""

    from ..component.st.stusb4500 import StUsb4500Nvm

    nvm = StUsb4500Nvm(Stusb4500Cli.sectors_parse(sectors))
    if output:
        yaml.safe_dump({"base": "default", **nvm.to_config()}, output, sort_keys = False)
    else:
        nvm.pretty(click.echo)

@stusb4500.command()
@click.argument('config', type = click.Path(exists = True, dir_okay = False))
def encode(config):
    """Encode customization from a YAML file with default base"""

    nvm = Stusb4500Cli.nvm_build(Stusb4500Cli.config_load(config), None)
    nvm.pretty(click.echo)
