from . import base
from ..protocol import smbus
import click

@base.cli.group(help = "SMBus manipulation", name = "smbus")
def smbus_():
    pass

@smbus_.command(help = "Perform ARP on bus")
@click.option('-r', '--root', "root", type = base.ROOT)
def arp(root):
    devices = root.arp()

    for addr, udid in sorted(devices.items()):
        print("%02x: %s" % (addr, udid.hex()))

@smbus_.command(help = "Perform SMBUS Send Byte")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("byte", type = base.HEX)
def send_byte(root, byte):
    assert isinstance(root, smbus.Slave)
    root.send_byte(byte)

@smbus_.command(help = "Perform SMBUS Receive Byte")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
def receive_byte(root):
    assert isinstance(root, smbus.Slave)
    print("%02x" % root.receive_byte())

@smbus_.command(help = "Perform SMBUS Write Byte")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
@click.argument("data", type = base.HEX)
def write_byte(root, command, data):
    assert isinstance(root, smbus.Slave)
    root.write_byte(command, data)

@smbus_.command(help = "Perform SMBUS Read Byte")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
def read_byte(root, command):
    assert isinstance(root, smbus.Slave)
    print("%02x" % root.read_byte(command))

@smbus_.command(help = "Perform SMBUS Write Word")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
@click.argument("data", type = base.HEX)
def write_word(root, command, data):
    assert isinstance(root, smbus.Slave)
    root.write_word(command, data)

@smbus_.command(help = "Perform SMBUS Read Word")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
def read_word(root, command):
    assert isinstance(root, smbus.Slave)
    print("%02x" % root.read_word(command))

@smbus_.command(help = "Perform SMBUS Process Call")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
@click.argument("data", type = str)
def process_call(root, command, data):
    assert isinstance(root, smbus.Slave)
    try:
        data = bytes.fromhex(data)
    except:
        print("Error: Not a valid hex byte string: %s" % data)
        return 1
    print(hex(root.process_call(command, data)))

@smbus_.command(help = "Perform SMBUS Block Write")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
@click.argument("data", type = str)
def block_write(root, command, data):
    assert isinstance(root, smbus.Slave)
    try:
        data = bytes.fromhex(data)
    except:
        print("Error: Not a valid hex byte string: %s" % data)
        return 1
    root.block_write(command, data)

@smbus_.command(help = "Perform SMBUS Block read")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
def block_read(root, command):
    assert isinstance(root, smbus.Slave)
    print(root.block_read(command).hex())

@smbus_.command(help = "Perform SMBUS Block Write Read")
@click.option('-r', '--root', help = "SMBUS device", type = base.ROOT)
@click.argument("command", type = base.HEX)
@click.argument("data", type = str)
def block_write(root, command, data):
    assert isinstance(root, smbus.Slave)
    try:
        data = bytes.fromhex(data)
    except:
        print("Error: Not a valid hex byte string: %s" % data)
        return 1
    print(root.block_write_read(command, data).hex())

