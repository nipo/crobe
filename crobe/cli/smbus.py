from . import base
import click

@base.cli.group(help = "SMBus manipulation")
@click.option('-r', '--root', "root", type = base.ROOT)
@click.pass_context
def smbus(ctx, root):
    ctx.obj["bus"] = root

@smbus.command(help = "Perform ARP on bus")
@click.pass_context
def arp(ctx):
    bus = ctx.obj["bus"]

    devices = bus.arp()

    for addr, udid in sorted(devices.items()):
        print("%02x: %s" % (addr, udid.hex()))
