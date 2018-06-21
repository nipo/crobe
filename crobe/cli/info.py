from . import base
import click
from ..adapter.model import Enumerator, Adapter

def component_dump(comp, prefix = ""):
    click.echo("%s %s" % (prefix, comp))
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
def enumerator_dump(e, prefix = ""):
    click.echo(prefix + "* Enumerator %s" % e)

    prefix += "  "

    for c in e.children:
        if isinstance(c, Enumerator):
            enumerator_dump(c, prefix)
        elif isinstance(c, Adapter):
            click.echo(prefix + "* Adapter %s supported interfaces: %s" % (c, ", ".join(c.supported_interfaces)))
        else:
            click.echo(prefix + "* ???? %s" % c)

@base.cli.group(help = "Informational")
def info():
    pass

@info.command(help = "Adapter list")
def adapters():
    Enumerator.singleton.start()
    enumerator_dump(Enumerator.singleton)

@info.command(help = "Component tree enumerator")
@base.roots()
@base.field()
@click.option("--cpuid", is_flag = True)
def enumerate(roots, field, cpuid):
    from ..adapter.model import Enumerator

    click.echo(" Roots")
    for r in roots:
        component_dump(r, "  ")

    component_dump(field)

    if cpuid:
        from ..component.arm.cpuid import CpuidDumper
        from ..component.arm.cortex import Cortex
        cortexes = field.children_of_class(Cortex)
        for c in cortexes:
            CpuidDumper(c.scs).dump(click.echo)

@info.command(help = "I2C bus scan")
@base.roots()
@click.option("--first", callback = base.hex_parse, default = 0x01, help = "First address to scan")
@click.option("--last", callback = base.hex_parse, default = 0x7f, help = "Last address to scan")
@click.option("--addr", callback = base.hex_parse_list, help = "Explicitly add address to scan", multiple = True)
def i2c_scan(roots, first, last, addr):
    from ..protocol.i2c import AddressNack
    addresses = list(addr or range(first, last + 1))

    bus = roots[0]

    for addr in addresses:
        try:
            bus.write(addr, b'')
        except AddressNack:
            continue
        click.echo("Slave on address %02x" % addr)
