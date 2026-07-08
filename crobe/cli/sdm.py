"""Agilex SDM interaction CLI commands."""

from pathlib import Path

import click

from . import base
from ..component.altera.sdm import Sdm
from ..component.altera.sdm_jtag import SdmJtag
from ..component.altera.agilex import Agilex

@base.cli.group(help="Agilex SDM operations")
def sdm():
    pass

@sdm.command(help="Get voltages")
@click.option('-r', '--root', type=base.ROOT, required=True,
              help='Path to JTAG Tap (e.g. tei-/jtag/0/0)')
def get_voltages(root):
    sdm_jtag = SdmJtag(root)
    sdm_jtag.sync()
    sdm_jtag.config_request()
    sdm_jtag.get_idcode()
    vs = sdm_jtag.get_voltages(Agilex.VoltageChannel)

    for key, value in vs.items():
        print(f"{key.name:9}: {value:.2f} V")

@sdm.command(help="Get temperatures")
@click.option('-r', '--root', type=base.ROOT, required=True,
              help='Path to JTAG Tap (e.g. tei-/jtag/0/0)')
def get_temperatures(root):
    sdm_jtag = SdmJtag(root)
    sdm_jtag.sync()
    t = sdm_jtag.get_temperatures(0,[0])
    if t[(0,0)] is not None:
        print(f"Max temperature in zone 0 {t[(0,0)]:.2f}°C")
    t = sdm_jtag.get_temperatures(1,[0])
    if t[(1,0)] is not None:
        print(f"Max temperature in zone 1 {t[(1,0)]:.2f}°C")
    t = sdm_jtag.get_temperatures(3,[0])
    if t[(3,0)] is not None:
        print(f"Max temperature in zone 3 {t[(3,0)]:.2f}°C")
    t = sdm_jtag.get_temperatures(4,[0])
    if t[(4,0)] is not None:
        print(f"Max temperature in zone 4 {t[(4,0)]:.2f}°C")