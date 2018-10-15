from . import base
from ..part_id import PartId
from ..bsdl.cache import Cache
import click
import glob

@base.cli.group(help = "Boundary scan")
def bscan():
    pass

@bscan.command(help = "Definition manipulation")
@click.option("--list", help = "List cache", is_flag = True)
@click.option("--rebuild", help = "Rebuild cache", is_flag = True)
@click.option("--id", help = "Filter by IDCODE", type = str, metavar = "IDCODE")
@click.option("--name", help = "Filter by name", type = str, metavar = "NAME")
@click.option("--pkg", help = "Filter by package", type = str, metavar = "PKG")
@click.option("--dump", help = "Dump component", is_flag = True)
def bsdl(list, rebuild, id, name, pkg, dump):
    cache = Cache.open()
    if rebuild:
        cache.rebuild()
        return

    for entity in cache.filter(name = name or None,
                               idcode = int(id, 16) if id else None,
                               package = pkg or None):
        if list:
            click.echo("- %s/%s: %s" % (entity.name, entity.package_variant,
                                   [PartId.from_idcode(c.value).pretty() for c in entity.id_codes]))

        if dump:
            entity.pprint()

@bscan.command(help = "Pin value poller")
@base.roots()
@click.option("--pkg", help = "Set packages for ICs in chain", type = str, metavar = "PKG,PKG", default = "")
@click.option("--ignore", help = "Ignore some IOs", type = str, metavar = "TAP/PIN,...", default = "")
def poll(roots, pkg, ignore):
    from ..bscan.dumper import Dumper

    packages = pkg.split(",")
    ignores = set()
    for tp in filter(None, ignore.split(',')):
        t, p = tp.split("/", 1)
        ignores.add((t, p))

    dumper = Dumper(roots[0], packages)
    dumper.run(ignores)

@bscan.command(help = "Pin set poller")
@base.roots()
@click.option("--pkg", help = "Set packages for ICs in chain", type = str, metavar = "PKG,PKG", default = "")
def ones(roots, pkg):
    from ..bscan.dumper import Dumper

    packages = pkg.split(",")
    dumper = Dumper(roots[0], packages)
    before = {}
    for d, tap in dumper.definitions:
        before[d.name] = set()

    while True:
        values = dumper.pin_values()
        for chip_name, chip in sorted(values.items()):
            pins = set()
            for pin, value in chip.items():
                if value:
                    pins.add(pin.name)
            if before[chip_name] != pins:
                if len(pins) > 10:
                    print(chip_name, "too_many")
                else:
                    print(chip_name, list(sorted(pins)))
                before[chip_name] = pins
