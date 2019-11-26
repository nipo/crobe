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

@ftdi.command(help = "EEPROM dumper")
@click.pass_context
@click.option("--size", type = base.HEX, default = 0x80, help = "Eeprom 16-bit word count")
def eeprom_dump_raw(ctx, size):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    entries = handle.eeprom_read_values(0, size)
    for i in range(0, size, 8):
        print("%03x" % (i * 2), end = " ")
        for j in entries[i : i+8]:
            print("%04x" % j, end = " ")
        blob = b''.join([x.to_bytes(2, "little") for x in entries[i : i+8]])
        for j in blob:
            print(chr(j) if 0x20 <= j <= 0x7f else ".", end = "")
        print()

    crc = 0xaaaa
    for e in entries[:-1]:
        crc ^= e
        crc = ((crc << 1) | (crc >> 15)) & 0xffff
    print("CRC: %04x" % crc)
        
@ftdi.command(help = "EEPROM Writer")
@click.option("--vid", type = base.HEX, required = True, help = "Vendor ID")
@click.option("--pid", type = base.HEX, required = True, help = "Product ID")
@click.option("--version", type = base.HEX, default = 0x0100, help = "Product version")
@click.option("--vendor", type = str, required = True, help = "Vendor name")
@click.option("--product", type = str, required = True, help = "Product name")
@click.option("--serial", type = str, required = True, help = "Serial number")
@click.option("--power", type = int, default = 500, help = "Power drain, mA (0 = self)")
@click.option("--mode", type = str, help = "Port modes (UART, FIFO, CPU, OPTO), comma separated",
              default = "FIFO,FIFO")
@click.pass_context
def eeprom_write(ctx, vid, pid, version, vendor, product, serial, power, mode):
    connection_id = ctx.obj["connection_id"]
    handle = Handle(connection_id, "A", "RESET")

    vendor = vendor.encode('ascii', 'ignore')
    product = product.encode('ascii', 'ignore')
    serial = serial.encode('ascii', 'ignore')
    mode_a, mode_b = map(str.upper, mode.split(',', 1))
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
