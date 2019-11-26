from . import base
import click
from ..adapter.ftdi.ftdi import FtdiError, Handle
from ..adapter.ftdi import api
from ..adapter.digilent import Serial

@base.cli.group(help = "Digilent probe handling")
@click.argument('connection', type = str)
@click.pass_context
def digilent(ctx, connection):
    bus, device = map(lambda x:int(x, 10), connection.split("/", 1))
    ctx.obj["connection_id"] = b"d:%03d/%03d" % (bus, device)
    
@digilent.command(help = "Serial/info dumper")
@click.pass_context
def serial_dump(ctx):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    raw = handle.eeprom_get()
    user_data = raw[0x14:0xa0]
    serial = Serial.from_bytes(user_data)
    serial.dump()
    assert raw.index(bytes(serial))

@digilent.command(help = "Serializer")
@click.option("--vendor", type = str, required = True, help = "Vendor name")
@click.option("--product", type = str, required = True, help = "Product name")
@click.option("--serial", type = str, required = True, help = "Serial number")
@click.option("--oemid", type = base.HEX, required = True, help = "OEM ID")
@click.option("--pdid", type = base.HEX, required = True, help = "PDID")
@click.option("--user-name", type = str, required = True, help = "User name")
@click.option("--product-name", type = str, required = True, help = "Product name")
@click.option("--power", type = int, default = 500, help = "Power")
@click.option("--dcap-pub", type = base.HEX, default = 0, help = "DCAP Public")
@click.option("--dcap-priv", type = base.HEX, default = 0, help = "DCAP Private")
@click.pass_context
def serialize(ctx, vendor, product, serial, oemid, pdid, user_name, product_name, power, dcap_pub, dcap_priv):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    vendor = vendor.encode('ascii', 'ignore')
    product = product.encode('ascii', 'ignore')
    serial = serial.encode('ascii', 'ignore')
    power = power or None

    info = Serial(oemid, pdid, user_name, product_name, dcap_pub, dcap_priv)
    
    handle.eeprom_reset_defaults(vendor, product, serial)
    handle.eeprom_power_set(power)
    handle.eeprom_user_data_set(bytes(info))
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            click.echo("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass

    if click.confirm("Write those values ?"):
        handle.eeprom_writeback()
        click.echo("Replug device for reenumeration")
