from . import base
import click
from ..protocol import swd
from ..component.nxp.mdm_ap import MdmAp

@base.cli.group(help = "Kinetis")
def kinetis():
    pass

@kinetis.command(help = "Unlock MKL03 using MDM-AP")
@click.option('-r', '--root', type = base.ROOT)
def unlock(root):
    print(root)
    root.erase_all()
    root.reset = True
    root.reset = True
    
