from . import base
import click
import yaml

@base.cli.group()
def max31760():
    "MAX31760-specific"

class Max31760Cli:
    @staticmethod
    def config_load(path):
        with open(path) as fd:
            config = yaml.safe_load(fd)
        if not isinstance(config, dict):
            raise click.ClickException(f"{path}: expected a mapping")
        return config

    @staticmethod
    def image_parse(text):
        from ..component.maxim.max31760 import Max31760Eeprom

        data = bytes.fromhex("".join(text.split()))
        if len(data) != Max31760Eeprom.SIZE:
            raise click.ClickException(f"Expected {Max31760Eeprom.SIZE} bytes, got {len(data)}")
        return data

    @staticmethod
    def eeprom_build(config, device_image):
        from ..component.maxim.max31760 import Max31760Eeprom

        config = dict(config)
        base_name = config.pop("base", None)
        if base_name == "default":
            base_image = Max31760Eeprom.DEFAULT
        elif base_name == "device":
            if device_image is None:
                raise click.ClickException("base: device needs a device")
            base_image = device_image
        else:
            raise click.ClickException("base must be either 'default' or 'device'")

        try:
            return Max31760Eeprom.from_config(config, base_image)
        except ValueError as e:
            raise click.ClickException(str(e))

    @staticmethod
    def diff_print(old, new):
        old_config = old.to_config()
        new_config = new.to_config()
        for k, v in new_config.items():
            if old_config[k] != v:
                click.echo(f"{k}: {old_config[k]} -> {v}")
        old_image = old.image()
        new_image = new.image()
        for addr in range(0, len(new_image), 16):
            o = old_image[addr:addr+16]
            n = new_image[addr:addr+16]
            if o != n:
                click.echo(f"{addr:02x}: {o.hex()} -> {n.hex()}")

    @staticmethod
    def config_write(eeprom, base_name, output):
        yaml.safe_dump({"base": base_name, **eeprom.to_config()}, output, sort_keys = False)

@max31760.command()
@click.option('-r', '--root', type = base.ROOT)
@click.option('-n', '--dry-run', is_flag = True, help = "Only show changes")
@click.argument('config', type = click.Path(exists = True, dir_okay = False))
def program(root, dry_run, config):
    """Program EEPROM from a YAML file"""

    from ..component.maxim.max31760 import Max31760, Max31760Eeprom

    assert isinstance(root, Max31760)

    current = Max31760Eeprom(root.eeprom_get())
    eeprom = Max31760Cli.eeprom_build(Max31760Cli.config_load(config), current.image())

    if eeprom.image() == current.image():
        click.echo("EEPROM already up to date")
        return

    Max31760Cli.diff_print(current, eeprom)
    if dry_run:
        return

    root.eeprom_set(eeprom.image())
    if root.eeprom_get() != eeprom.image():
        raise click.ClickException("EEPROM readback mismatch")
    click.echo("EEPROM programmed")

@max31760.command()
@click.option('-r', '--root', type = base.ROOT)
@click.option('-o', '--output', type = click.File('w'), help = "Write YAML config")
def dump(root, output):
    """Dump EEPROM"""

    from ..component.maxim.max31760 import Max31760, Max31760Eeprom

    assert isinstance(root, Max31760)

    eeprom = Max31760Eeprom(root.eeprom_get())
    if output:
        Max31760Cli.config_write(eeprom, "device", output)
    else:
        eeprom.pretty(click.echo)

@max31760.command()
@click.argument('image')
@click.option('-o', '--output', type = click.File('w'), help = "Write YAML config")
def decode(image, output):
    """Decode EEPROM from 80 hex bytes"""

    from ..component.maxim.max31760 import Max31760Eeprom

    try:
        eeprom = Max31760Eeprom(Max31760Cli.image_parse(image))
    except ValueError as e:
        raise click.ClickException(str(e))
    if output:
        Max31760Cli.config_write(eeprom, "default", output)
    else:
        eeprom.pretty(click.echo)

@max31760.command()
@click.argument('config', type = click.Path(exists = True, dir_okay = False))
def encode(config):
    """Encode EEPROM from a YAML file with default base"""

    eeprom = Max31760Cli.eeprom_build(Max31760Cli.config_load(config), None)
    eeprom.pretty(click.echo)
