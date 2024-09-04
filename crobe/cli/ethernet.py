from . import base
from ..util.pretty import metric
import click

@base.cli.group(help = "Ethernet fiddling")
def ethernet():
    pass

@ethernet.command(help = "Run cable diagnostics through PHY MII")
@click.option('-r', '--root', type = base.ROOT)
def tdr(root):
    result = root.tdr_execute()
    for r in result:
        print(r)

@ethernet.command(help = "Dump RTL8211 register map")
@click.option('-r', '--root', type = base.ROOT)
def rtl8211_dump(root):
    from ..component.realtek.rtl8211 import Rtl8211, Register
    from ..protocol.smi import C22Read

    for page in list(range(0xa40, 0xa48)) + list(range(0xd00, 0xd10)):
        ops = []
        for addr in range(page << 3, (page+1) << 3):
            ops.append(root.cmd_read(addr))

        root.execute(ops)

        n = 0
        for o in ops:
            if not isinstance(o, C22Read):
                continue
            if n % 8 == 0:
                print(f"{o.addr >> 3:#06x}:", end = "")
            print(f" {o.data:#06x}", end = "")
            if n % 8 == 7:
                print()
            n += 1
