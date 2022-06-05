from . import base
import click
import binascii
import struct

@base.cli.group(help = "Memory manipulation")
@click.option('-r', '--root', type = base.ROOT)
@click.pass_context
def memory(ctx, root):
    ctx.obj["bus"] = root

@memory.command(help = "Arbitrary setter")
@click.option('--raw', metavar = 'ADDRESS=DATA',
              type = str, multiple = True,
              help = 'Blob write')
@click.option('--reg32', metavar = 'ADDRESS=VALUE',
              type = str, multiple = True,
              help = 'Register to poke')
@click.pass_context
def poke(ctx, raw, reg32):
    bus = ctx.obj["bus"]
    to_write = []

    for item in raw:
        address, value = item.split("=", 1)
        address = int(address, 16)
        data = binascii.a2b_hex(value.replace(" ", ""))
        to_write.append((address, data))

    for item in reg32:
        address, value = item.split("=", 1)
        address = int(address, 16)
        data = struct.pack("<L", int(value, 16))
        to_write.append((address, data))

    for address, data in to_write:
        click.echo("0x%08x: %s" % (address, binascii.b2a_hex(data)))
        bus.mem_write(address, data)

@memory.command(help = "Arbitrary setter from blob")
@click.argument('address', metavar = 'ADDRESS', type = str)
@click.argument('file', type = click.File('rb'))
@click.pass_context
def write(ctx, address, file):
    bus = ctx.obj["bus"]
    address = int(address, 16)
    data = file.read()
    bus.mem_write(address, data)

@memory.command(help = "Arbitrary getter")
@click.argument('address', metavar = 'ADDRESS', type = str)
@click.argument('size', metavar = 'size', type = str, default = "4")
@click.pass_context
def peek(ctx, address, size):
    bus = ctx.obj["bus"]
    address = int(address, 16)
    size = int(size, 0)
    click.echo("Bus: %s" % bus)

    data = bus.mem_read(address, size)
    click.echo(hex(address) + " " + str(binascii.b2a_hex(data), "ascii"))

@memory.command(help = "Longer arbitrary getter")
@click.argument('address', metavar = 'ADDRESS', type = str)
@click.argument('size', metavar = 'size', type = str, default = "4")
@click.pass_context
def hexdump(ctx, address, size):
    bus = ctx.obj["bus"]
    address = int(address, 16)
    size = int(size, 0)

    data = bus.mem_read(address, size)
    from ..util.hexdump import hexdump

    hexdump(address, data, printer = print)
