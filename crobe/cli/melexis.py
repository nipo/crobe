from . import base
import click
import binascii
import math
import time

@base.cli.group(help = "Melexis helpers")
def melexis():
    pass

@melexis.command(help = "Poll temperatures")
@click.option('-r', '--root', type = base.ROOT)
def temp_poll(root):
    while True:
        try:
            values = root.sensors_read()
            for name, k in values.items():
                print("%s: %3.5f C" % (name, k - 273.15), end = ", ")
            print()
        except:
            pass
        time.sleep(.5)
