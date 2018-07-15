from . import base
import click
import binascii
import math
import time

@base.cli.group(help = "WS2812 Hacks")
def ws2812():
    pass

def color_code(r, g, b):
    color_word = b''
    for byte in [g, r, b]:
        for bit in range(7, -1, -1):
            if byte & (1 << bit):
                color_word += b'c'
            else:
                color_word += b'8'
    return binascii.a2b_hex(color_word)

@ws2812.command(help = "Set color")
@base.roots()
@click.argument("color", type = str)
@click.argument("count", type = int)
def set(roots, color, count):
    color = int(color, 16)
    r = (color >> 16) & 0xff
    g = (color >> 8) & 0xff
    b = color & 0xff

    reset_word = b'\x00' * 30
    data = reset_word + color_code(r, g, b) * count

    roots[0].freq_cap("ws2812", 10e6)
    roots[0].shift(data, read_miso = False)

@ws2812.command(help = "Rotate colors")
@base.roots()
@click.argument("count", type = int)
def rotate(roots, count):
    reset_word = b'\x00' * 40

    angle = 0
    while True:
        angle += math.pi / 60

        r = int(math.cos(angle) * 127 + 127)
        g = int(math.cos(angle + math.pi * 2 / 3) * 127 + 127)
        b = int(math.cos(angle + math.pi * 4 / 3) * 127 + 127)

        print(r, g, b)
        data = reset_word + color_code(r, g, b) * count

        roots[0].freq_cap("ws2812", 10e6)
        roots[0].shift(data, read_miso = False)
        time.sleep(.01)
