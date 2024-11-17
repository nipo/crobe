from . import base
import click
from ..component.xilinx import zynq, series67, series7, xadc
import binascii
import time

@base.cli.group(help = "Xilinx-specific")
def xilinx():
    pass

@xilinx.command(help = "BBRAM key setter")
@click.option('-r', '--root', type = base.ROOT)
@click.argument("key", type = str)
def bbram_key_set(root, key):
    assert isinstance(root, zynq.Zynq)

    key = binascii.a2b_hex(key.encode("ascii"))
    assert len(key) == 32

    click.echo("Target: %s" % root)

    root.bbram_open()
    root.bbram_key_write(key)
    rbkey = root.bbram_key_read()
    root.bbram_close()

    assert key == rbkey

@xilinx.command(help = "Info dumper")
@click.option('-r', '--root', type = base.ROOT)
def info(root):
    assert isinstance(root, series67.Series67)

    if root.done:
        click.echo("Device is running, not accessing config port")
        return

    root.cfg_status_dump()
    if isinstance(root, series7.Series7):
        root.bbram_open()
        rows = []
        for row in range(0x20):
            rows.append(root.efuse_row_read(row))

        pretty = {}
        for i in range(32):
            try:
                pretty[i] = getattr(root, "Efuse%d" % i)
            except AttributeError:
                pass
            
        for i, r in enumerate(rows):
            print(" Efuse%d, 0x%08x" % (i, r))
            if (root.efuse_ecc_update(r) ^ r) & 0x3fffffff:
                print("  ECC Failure: differences = 0x%08x" % (root.efuse_ecc_update(r) ^ r))
                  
            if i in pretty:
                dumper = pretty[i](all = r)
                dumper.dump_pretty(print)

@xilinx.command(help = "Efuse key setter")
@click.option('-r', '--root', type = base.ROOT)
@click.argument("key", type = str, default = "")
@click.option("--protect", is_flag = True)
def efuse_key_set(root, key, protect):
    assert isinstance(root, zynq.Zynq)

    click.echo("Target: %s" % root)

    if key:
        root.bbram_open()
        key = binascii.a2b_hex(key.encode("ascii"))
        assert len(key) == 32
        root.efuse_key_write(key)
        root.bbram_close()

        root.bbram_open()
        rbkey = root.efuse_key_read()
        root.bbram_close()
        if key != rbkey:
            x = bytes([a^b for (a,b) in zip(key, rbkey)])
            print("Differencies at readback:", binascii.b2a_hex(x))
            if protect:
                print("Not protecting key")
            return 1

    if protect:
        root.bbram_open()
        root.efuse_cfg_set(root.FUSE_CFG_KEY_PROTECT_WRITE)
        root.efuse_cfg_set(root.FUSE_CFG_KEY_PROTECT_READ)
        root.bbram_close()

@xilinx.command(help = "EFUSE dumper")
@click.option('-r', '--root', type = base.ROOT)
def efuse_dump(root):
    root.bbram_open()
    click.echo("Target: %s" % root)
    for row in range(0x20):
        value = root.efuse_row_read(row)
        try:
            pretty = getattr(root, "Efuse%d" % row)
            pretty(value).dump()
        except AttributeError:
            click.echo(" Efuse%d, 0x%08x%s" % (row, value, "" if root.efuse_ecc_update(value) == value else " ECC Fail"))
    rbkey = root.efuse_key_read()
    print("Key:", binascii.b2a_hex(rbkey))
        
    root.bbram_close()

@xilinx.command(help = "XADC Temperature monitor")
@click.option('-r', '--root', type = base.ROOT)
def xadc_temp(root):
    z = root
    assert isinstance(z, xadc.Xadc)

    z.xadc_init_defaults()
    while True:
        print("Temperature: %3.2f°C" % z.xadc_temperature_read(), end = "\r")
        time.sleep(.1)

@xilinx.command(help = "XADC Poller")
@click.option("--enable", is_flag = True)
@click.option('-r', '--root', type = base.ROOT)
@click.option('-c', '--channel', type = int)
@click.option('-o', '--offset', type = float, default = 0.)
@click.option('-s', '--scale', type = float, default = 1.)
def xadc_poll(root, channel, offset, scale, enable):
    z = root
    assert isinstance(z, xadc.Xadc)

    z.xadc_init_defaults()
    if enable:
        z.xadc_write(2, 1)
        if channel <= 15:
            z.xadc_write(0x48, 1 << channel)
#            z.xadc_write(0x4c, 1 << channel)
            z.xadc_write(0x4c, 0)
        else:
            z.xadc_write(0x49, 1 << (channel - 16))
#            z.xadc_write(0x4d, 1 << (channel - 16))
            z.xadc_write(0x4d, 0)
        z.xadc_write(z.XADC_REG_CONFIG(1), z.XADC_CFG1_SEQ(z.XADC_SEQ_CONTINUOUS))
    while True:
        v = z.xadc_value_read(channel) * scale + offset
        print("Value: %1.5f" % v, end = "\r")
        time.sleep(.1)

@xilinx.command(help = "Xilinx Virtual Cable server")
@click.option("--port", type = int, default = 2542, help = "TCP port to bind")
@click.option('-r', '--root', type = base.ROOT)
def vcd_server(root, port):
    from ..protocol.jtag import Interface
    from ..xvcd.server import XvcdServer
    from ..util.pretty import metric

    intf = root

    if not isinstance(intf, Interface):
        raise ValueError("Expected a JTAG interface. Try -r [adapter]/jtag.")
    
    click.echo("Freq: %s" % metric(intf.freq, "Hz"))

    try:
        intf.reset = False
    except NotImplementedError:
        pass
    XvcdServer(port, intf).serve()

@xilinx.command(help = "Dump Series 7 bitstream")
@click.argument("program", type = base.PROGRAM)
def s7_dump(program):
    from ..component.xilinx.bitstream import Bitstream

    bs = Bitstream.from_loadable(program)
    for packet in bs.packets:
        print(packet)

@xilinx.command(help = "Change Series 7 bitstream target IDCODE")
@click.argument("source", type = base.PROGRAM)
@click.argument("idcode", type = base.HEX)
@click.argument("destination", type = click.File('wb'))
def s7_idcode_change(source, idcode, destination):
    from ..component.xilinx.bitstream import Bitstream

    bs = Bitstream.from_loadable(source)

    from ..protocol.jtag import Chain
    from ..part_id import PartId
    part_id = PartId.from_idcode(idcode).drop_revision()
    tap = Chain.db.call(part_id, None, part_id)

    new_bs = bs.with_idcode(int(part_id))
    name = tap.name.lower()
    if name.startswith("xc"):
        name = name[2:]
    new_bs.header_info["device"] = name
    
    destination.write(new_bs.to_bit())
