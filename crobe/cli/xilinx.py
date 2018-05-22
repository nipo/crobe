from . import base
import click
from ..component.xilinx import zynq
import binascii
import time

@base.cli.group(help = "Xilinx-specific")
def xilinx():
    pass

@xilinx.command(help = "BBRAM key setter")
@base.roots()
@click.argument("key", type = str)
def bbram_key_set(roots, key):
    root = roots[0]
    assert isinstance(root, zynq.Zynq)

    key = binascii.a2b_hex(key.encode("ascii"))
    assert len(key) == 32

    click.echo("Target: %s" % root)

    root.bbram_open()
    root.bbram_key_write(key)
    rbkey = root.bbram_key_read()
    root.bbram_close()

    assert key == rbkey

@xilinx.command(help = "EFUSE dumper")
@base.roots()
def efuse_dump(roots):
    root = roots[0]
    assert isinstance(root, zynq.Zynq)

    root.bbram_open()
    click.echo("Target: %s" % root)
    for row in range(0x1f):
        value = root.efuse_row_read(row)
        try:
            pretty = getattr(root, "Efuse%d" % row)
            pretty(value).dump()
        except AttributeError:
            click.echo(" Efuse%d, 0x%08x" % (row, value))
        
    root.bbram_close()

@xilinx.command(help = "XADC Temperature monitor")
@base.roots()
def xadc_temp(roots):
    z = roots[0]
    assert isinstance(z, zynq.Zynq)

    z.xadc_init_defaults()
    while True:
        print("Temperature: %3.2f°C" % z.xadc_temperature_read(), end = "\r")
        time.sleep(.1)

@xilinx.command(help = "Xilinx Virtual Cable server")
@click.option("--port", type = int, default = 2542, help = "TCP port to bind")
@base.roots()
def vcd_server(roots, port):
    from ..protocol.jtag import Interface
    from ..xvcd.server import XvcdServer
    from ..util.pretty import metric

    intf = roots[0]

    if not isinstance(intf, Interface):
        raise ValueError("Expected a JTAG interface. Try -e [adapter]/jtag.")
    
    click.echo("Adapter: %s" % intf.port.firmware_info)
    click.echo("Serial: %s" % intf.port.serial_number)
    click.echo("Freq: %s" % metric(intf.freq, "Hz"))

    try:
        intf.reset = False
    except NotImplementedError:
        pass
    XvcdServer(port, intf).serve()
