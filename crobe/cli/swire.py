from . import base as base
from ..protocol import swire
import click
import time

@base.cli.group(help = "SWIRE manipulation", name = "swire")
def swire_():
    pass

@swire_.command(help = "Init baudrate and perform a readback")
@click.option('-r', '--root', help = "Swire device", type = base.ROOT)
def ping(root):
    sid = 0
    delay = 500

    root.execute([root.cmd_reset(True)])
    time.sleep(.010)
    div = int(24e6 / root.freq / 6)
    print(root.freq, div)

    r = root.cmd_read(sid, 0x007e, 2)
    r2 = root.cmd_read(sid, 0x00b2, 1)

    root.execute([
        root.cmd_reset(False),
        ])
    time.sleep(.001 * delay)
    root.execute([
        root.cmd_write(sid, 0x0602, b"\x05"),
        root.cmd_write(sid, 0x00b2, bytes([div])),
        r, r2,
    ])

    print("sid", sid)
    print("id", r.data)
    print("div", r2.data)
