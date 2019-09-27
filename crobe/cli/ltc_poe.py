from . import base
import click
import binascii
import math
import time

@base.cli.group(help = "LTC PoE control")
def ltc_poe():
    pass

@ltc_poe.command(help = "Get ports status")
@click.option('-r', '--root', type = base.ROOT)
def status(root):
    for i in range(root.port_count):
        s, c = root.port_status_get(i)
        v = root.port_voltage_get(i)
        a = root.port_current_get(i)
        print("Port %d, %s, %s, %1.2fV, %1.2fA" % (i + 1, s, c, v, a))

@ltc_poe.command(help = "Set port power")
@click.option('-r', '--root', type = base.ROOT)
@click.argument("port", type = int)
@click.argument("what", type = str)
def port_set(root, port, what):
    if what == "off":
        root.port_disable(port-1)
    elif what == "cycle":
        root.port_disable(port-1)
        time.sleep(.3)
        root.port_auto_enable(port-1)
    elif what == "on":
        root.port_auto_enable(port-1)
    else:
        raise ValueError(what)
