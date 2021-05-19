from . import base
import click
from ..adapter.model import HwRoot, Enumerator, Adapter

def component_dump(comp, prefix = ""):
    click.echo("%s %s" % (prefix, comp))
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
def enumerator_dump(e, prefix = ""):
    click.echo(prefix + "* %s" % e)

    prefix += "  "

    for c in e.children:
        if isinstance(c, Enumerator):
            enumerator_dump(c, prefix)
        elif isinstance(c, Adapter):
            click.echo(prefix + "* %s, interfaces: %s" % (c, ", ".join(c.supported_interfaces)))
        else:
            click.echo(prefix + "* ???? %s" % c)

@base.cli.group(help = "Informational")
def info():
    pass

@info.command(help = "Adapter list")
def adapters():
    HwRoot.start_root()
    enumerator_dump(HwRoot)

@info.command(help = "Component tree enumerator")
@click.option('-r', '--root', "roots", type = base.ROOT, multiple = True)
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
@click.option('-r', '--root', type = base.ROOT)
@click.option("--write", help = "Use a zero-byte write operation. This may not be supported by all masters", is_flag = True)
@click.option("--first", type = base.HEX, default = 0x01, help = "First address to scan")
@click.option("--last", type = base.HEX, default = 0x7f, help = "Last address to scan")
@click.option("--addr", type = base.HEX, help = "Explicitly add address to scan", multiple = True)
def i2c_scan(root, first, last, addr, write):
    from ..protocol.i2c import AddressNack
    addresses = list(addr or range(first, last + 1))

    for addr in addresses:
        try:
            if write:
                root.write(addr, b'')
            else:
                root.read(addr, 1)
        except AddressNack:
            continue
        click.echo("Slave on address %02x" % addr)
