from . import base
import click
import binascii
import math
import time

@base.cli.group(help = "PLL Control")
def pll():
    pass

@pll.command(help = "Dump config/status")
@click.option('-r', '--root', type = base.ROOT)
@click.option('-c', '--clkin', type = float, default = None)
@click.option('-x', '--xtal', type = float, default = None)
@click.option('-p', '--primary', type = float, default = None)
@click.option('-s', '--secondary', type = float, default = None)
def dump(root, clkin, xtal, primary, secondary):
    args = {}
    if clkin is not None:
        args["clkin"] = clkin
    if xtal is not None:
        args["xtal"] = xtal
    if primary is not None:
        args["pri"] = primary
    if secondary is not None:
        args["sec"] = secondary
    root.state_dump(**args)

