from . import base
import click
import binascii
import math
import time

@base.cli.group(help = "PLL Control")
def pll():
    pass

@pll.command(help = "Dump SI5351 config/status")
@click.option('-r', '--root', type = base.ROOT)
@click.option('-c', '--clkin', type = float, default = 0.)
@click.option('-x', '--xtal', type = float, default = 0.)
def si5351_dump(root, clkin, xtal):
    root.state_dump(clkin = clkin * 1e6, xtal = xtal * 1e6)

