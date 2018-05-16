from . import base
import click
from ..adapter.ftdi.ftdi import FtdiError, Handle
from ..adapter.ftdi import api

@base.cli.group(help = "FTDI manipulation")
@click.argument('connection', type = str)
@click.pass_context
def ftdi(ctx, connection):
    bus, device = map(lambda x:int(x, 10), connection.split("/", 1))
    ctx.obj["connection_id"] = b"d:%03d/%03d" % (bus, device)

@ftdi.command(help = "Busblaster serializer")
@click.pass_context
def busblaster(ctx):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")
    
    try:
        raw = handle.eeprom_get()
        for i in range(0, len(raw), 16):
            click.echo("%02x:  %s" % (i, " ".join(map("%02x".__mod__, raw[i:i+16]))))
    except Exception:
        click.echo("No valid data found in EEPROM")
        return
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            click.echo("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass

@ftdi.command(help = "EEPROM dumper")
@click.pass_context
def eeprom_dump(ctx):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    try:
        raw = handle.eeprom_get()
        for i in range(0, len(raw), 16):
            click.echo("%02x:  %s" % (i, " ".join(map("%02x".__mod__, raw[i:i+16]))))
    except Exception:
        click.echo("No valid data found in EEPROM")
        return
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            click.echo("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass

@ftdi.command(help = "EEPROM Writer")
@click.option("--vid", type = str, required = True, help = "Vendor ID")
@click.option("--pid", type = str, required = True, help = "Product ID")
@click.option("--version", type = str, default = "0100", help = "Product version")
@click.option("--vendor", type = str, required = True, help = "Vendor name")
@click.option("--product", type = str, required = True, help = "Product name")
@click.option("--serial", type = str, required = True, help = "Serial number")
@click.option("--power", type = int, default = 500, help = "Power drain, mA (0 = self)")
@click.option("--mode", type = str, help = "Port modes (UART, FIFO, CPU, OPTO), comma separated",
              default = "FIFO,FIFO")
@click.pass_context
def eeprom_write(connection_id, vid, pid, version, vendor, product, serial, power, mode):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    vendor = vendor.encode('ascii', 'ignore')
    product = product.encode('ascii', 'ignore')
    serial = serial.encode('ascii', 'ignore')
    mode_a, mode_b = map(str.upper, mode.split(',', 1))
    vid = int(vid, 16)
    pid = int(pid, 16)
    version = int(version, 16)
    power = power or None

    handle.eeprom_strings_set(vendor, product, serial)
    handle.eeprom_vpv_set(vid, pid, version)
    handle.eeprom_power_set(power)
    handle.eeprom_channel_mode_set(mode_a, mode_b)
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            click.echo("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass

    if click.confirm("Write those values ?"):
        handle.eeprom_writeback()
        click.echo("Replug device for reenumeration")
