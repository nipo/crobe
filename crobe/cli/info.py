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

@info.command(help = "Check JTAG chain at all possible frequencies")
@click.option('-r', '--root', help = "JTAG interface", type = base.ROOT, multiple = False)
@click.option("--fmin", type = int, help = "Minimal frequency", default = 1000)
@click.option("--fmax", type = int, help = "Maximal frequency", default = 100000000)
@click.option("--step", type = int, help = "Frequency step", default = 1000)
@click.option("--ir", type = int, help = "Chain IR reg to test on", default = -1)
def jtag_frequency_test(root, fmin, fmax, step, ir):
    from ..protocol.jtag import Interface
    assert isinstance(root, Interface)
    from ..util.pretty import metric

    root.start()

    for low, high, ok in root.freq_test(fmin, fmax, step, ir):
        print(f"Frequencies {metric(low, 'Hz')}-{metric(high, 'Hz')}: {'OK' if ok else 'Fails'}")

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
