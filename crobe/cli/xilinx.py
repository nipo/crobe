from . import base
import click
from ..component.xilinx import zynq, series67
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

@xilinx.command(help = "Info dumper")
@base.roots()
def info(roots):
    root = roots[0]
    assert isinstance(root, series67.Series67)

    if root.done:
        click.echo("Device is running, not accessing config port")
        return

    root.cfg_status_dump()

@xilinx.command(help = "Efuse key setter")
@base.roots()
@click.argument("key", type = str, default = "")
@click.option("--protect", is_flag = True)
def efuse_key_set(roots, key, protect):
    root = roots[0]
    assert isinstance(root, zynq.Zynq)

    click.echo("Target: %s" % root)

    if key:
        root.bbram_open()
        key = binascii.a2b_hex(key.encode("ascii"))
        assert len(key) == 32
        root.efuse_key_write(key)
        root.bbram_close()

        root.bbram_open()
        rbkey = root.efuse_key_read()
        root.bbram_close()
        if key != rbkey:
            x = bytes([a^b for (a,b) in zip(key, rbkey)])
            print("Differencies at readback:", binascii.b2a_hex(x))
            if protect:
                print("Not protecting key")
            return 1

    if protect:
        root.bbram_open()
        root.efuse_cfg_set(root.FUSE_CFG_KEY_PROTECT_WRITE)
        root.efuse_cfg_set(root.FUSE_CFG_KEY_PROTECT_READ)
        root.bbram_close()

@xilinx.command(help = "EFUSE dumper")
@base.roots()
def efuse_dump(roots):
    root = roots[0]

    root.bbram_open()
    click.echo("Target: %s" % root)
    for row in range(0x20):
        value = root.efuse_row_read(row)
        try:
            pretty = getattr(root, "Efuse%d" % row)
            pretty(value).dump()
        except AttributeError:
            click.echo(" Efuse%d, 0x%08x%s" % (row, value, "" if root.efuse_ecc_update(value) == value else " ECC Fail"))
    rbkey = root.efuse_key_read()
    print("Key:", binascii.b2a_hex(rbkey))
        
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
