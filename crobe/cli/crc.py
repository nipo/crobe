from . import base
from ..util.crc import Crc
from ..util.bytes_ops import xor_
import click
from collections import defaultdict

@base.cli.group(help = "CRC tools")
def crc():
    pass

@crc.command()
@click.argument("alg", type = str)
@click.argument("data", type = str)
def init_recover(data, alg):
    """
    Assuming a blob with correct CRC appended, recover initial value
    """
    crc_alg = Crc.from_desc_string(alg)
    data = bytes.fromhex(data)
    init_state = crc_alg._backward_bytes(crc_alg.check_state, data)
    print(f"{init_state:x}")

@crc.command()
@click.argument("alg", type = str)
@click.argument("data", type = str)
@click.option("--init", type = base.HEX, default = None, help = "Initial CRC state (defaults to algorithm's default)", metavar = "HEX_VALUE")
def calculate(data, alg, init):
    """
    Calculate CRC of a small blob
    """
    crc_alg = Crc.from_desc_string(alg)
    data = bytes.fromhex(data)
    state = crc_alg(init)
    state.update(data)
    print(f"State: {state.state:#x}")
    print(f"Output as integer: {int(state):#x}")
    print(f"Output as bytes:   {bytes(state).hex()}")

@crc.command()
@click.argument("alg", type = str)
@click.argument("data", type = str)
@click.option("--init", type = base.HEX, default = None, help = "Initial CRC state (defaults to algorithm's default)", metavar = "HEX_VALUE")
def validate(data, alg, init):
    """
    Check a piece of data passes CRC validation
    """
    crc_alg = Crc.from_desc_string(alg)
    data = bytes.fromhex(data)
    state = crc_alg(init)
    state.update(data)
    if not state.is_valid():
        print("Invalid")
        raise click.exceptions.Exit(1)

@crc.command()
@click.argument("alg", type = str)
@click.argument("data", type = str)
@click.option("--init", type = base.HEX, default = None, help = "Initial CRC state (defaults to algorithm's default)", metavar = "HEX_VALUE")
def recover(alg, data, init):
    """For a payload with CRC, try to fix a 1 or 2-bit transmission error.

    When numbering bits in the message, bytes are taken in data order,
    bits from lsb.

    """
    alg = Crc.from_desc_string(alg)
    data = bytes.fromhex(data)

    crc_diff = alg.state_error(data, init = init)
    if crc_diff == 0:
        print("CRC is OK")
        return

    fixes = defaultdict(list)
    bit_contribution = alg.bit_contributions(len(data))

    for bit, contribution in bit_contribution.items():
        fixes[contribution].append((bit, ))

        for second in range(bit + 1, len(data) * 8):
            fixes[bit_contribution[second] ^ contribution].append((bit, second))

    if crc_diff not in fixes:
        print("Cannot recover bit flips")
        return

    for changed_bits in fixes[crc_diff]:
        print(f"Changing bits {changed_bits}:")
        mask = bytearray(len(data))
        for b in changed_bits:
            mask[b //8] ^= 1 << (b & 7)
        new_blob = xor_(data, mask)
        print(f" Mask  {mask.hex()}")
        print(f" Fixed {new_blob.hex()}")

        assert alg.is_valid(new_blob)
    
@crc.command()
@click.argument("data", type = str)
@click.argument("output", type = str)
@click.option("--width", type = int, metavar = "BIT_COUNT", help = "CRC state/poly bit count")
@click.option("--init", type = base.HEX, default = None, help = "Initial CRC state (defaults to algorithm's default)", metavar = "HEX_VALUE")
@click.option("--poly", type = base.HEX, metavar = "HEX_VALUE", help = "Polynom as an integer")
@click.option("--swap4", is_flag = True, help = "Swap bytes four-by-four before sending them to the CRC computation")
def find_parameters(data, output, width, poly, init, swap4):
    """Find actual parameters of CRC.

    Polynom, initial value, sample data and result CRC are needed.

    All combinations of bit order, polynom bit to coefficient order
    and pre/post state complementation are tried to find a set of
    algorithm parameters that matches the sample.

    """
    from crobe.util.endian import swib, swap

    try:
        data = bytes.fromhex(data)
    except ValueError:
        from ..loadable.model import Program
        p = Program.from_file(data)
        data = p[0].data

    value_bytes = bytes.fromhex(output)
    value = int.from_bytes(value_bytes, "little")

    if swap4:
        data = b"".join(data[i:i+4][::-1] for i in range(0, len(data), 4))

    mask = (1 << width) - 1
    outputs = [value]
    outputs += [swap(i, width) for i in outputs]
    outputs += [swib(i, width) for i in outputs]
    outputs += [i ^ mask for i in outputs]
    inits = [init]
    inits += [swap(i, width) for i in inits]
    inits += [swib(i, width) for i in inits]
    inits += [i ^ mask for i in inits]
    polys = []
    for p in [poly & mask, swib(poly & mask, width)]:
        polys.append((1 << width) | p)
        polys.append((p << 1) | 1)

    matching = set()

    for _poly in polys:
        if not _poly & 1:
            continue
        if not _poly & (1 << width):
            continue

        for pop_lsb in [False, True]:
            for order0_at_lsb in [False, True]:
                for complement_input in [False, True]:
                    crc_alg = Crc(
                        init = 0,
                        complement_state = False,
                        spill_bitswap = False,
                        spill_byte_order = "little",

                        poly = _poly,
                        pop_lsb = pop_lsb,
                        order0_at_lsb = order0_at_lsb,
                        complement_input = complement_input,
                    )

                    data_contribution = crc_alg._forward_bytes(0, data)
                    for init in inits:
                        init_contribution = crc_alg._forward_many(init, 8 * len(data))
                        if data_contribution ^ init_contribution in outputs:
                            matching.add(crc_alg.variant(init = init))
                            matching.add(crc_alg.variant(init = init ^ mask))

    ok = set()
    for crc_alg in matching:
        for complement_state in [False, True]:
            for spill_bitswap in [False, True]:
                for spill_byte_order in ["little", "big"]:
                    alg = crc_alg.variant(
                        complement_state = complement_state,
                        spill_byte_order = spill_byte_order,
                        spill_bitswap = spill_bitswap,
                    )
                    v = alg.calc_bytes(data)
                    if v == value_bytes:
                        ok.add(alg)

    for index, crc_alg in enumerate(ok):
        if index:
            print()
        print(f"Option #{index+1}:")
        print_alg_info(crc_alg)

@crc.command(short_help = "Compute CRC or data patch after modification in a blob",
             epilog = """
Let's suppose we have the following payload and its CRC:

\b
$ crobe loadable hexdump example.bin
0x00000000: 48 c9 bf 0e 80 6b b7 77 5f 03 b3 22 a4 ea a9 1e | H....k.w_.."....
0x00000010: 33 4b 59 f3 fb dd 83 7f ec fa 06 44 60 fb cf 20 | 3KY.......D`..
0x00000020: 55 ee 62 56 1f b2 42 bd b2 aa bc 20 56 e8 b8 a0 | U.bV..B.... V...
0x00000030: e4 62 ad 8b 40 70 d7 73 a8 0c bb ff 89 a7 90 c4 | .b..@p.s........
0x00000040: e5 be 46 60 86 1c 84 c9 7d 53 6f 46 34 64 ed e0 | ..F`....}SoF4d..
0x00000050: 47 81 41 60 5a 86 d3 fa e1 d1 10 1e 57 b4 15 7c | G.A`Z.......W..|
0x00000060: 6f aa 6c 71 ae c4 f5 88 50 80 26 0f be 9d 24 ac | o.lq....P.&...$.
0x00000070: 4d fc a0 82 b3 b6 87 35 b3 d6 a8 35 cc 62 bd d5 | M......5...5.b..
$ crobe loadable crc ethernet_fcs example.bin
example.bin None <0x0:0x80>: ba7d7de2

Let's say we want to replace six bytes at 0x40 to be [C0 DE DE AD F0 0D]:

\b
$ crobe loadable to-bin example.bin c0dedeadf00d:literal:+0x40 example-patched.bin

We now have the following binary and its new CRC:

\b
$ crobe loadable hexdump example-patched.bin
0x00000000: 48 c9 bf 0e 80 6b b7 77 5f 03 b3 22 a4 ea a9 1e | H....k.w_.."....
0x00000010: 33 4b 59 f3 fb dd 83 7f ec fa 06 44 60 fb cf 20 | 3KY.......D`..
0x00000020: 55 ee 62 56 1f b2 42 bd b2 aa bc 20 56 e8 b8 a0 | U.bV..B.... V...
0x00000030: e4 62 ad 8b 40 70 d7 73 a8 0c bb ff 89 a7 90 c4 | .b..@p.s........
0x00000040: c0 de de ad f0 0d 84 c9 7d 53 6f 46 34 64 ed e0 | ........}SoF4d..
0x00000050: 47 81 41 60 5a 86 d3 fa e1 d1 10 1e 57 b4 15 7c | G.A`Z.......W..|
0x00000060: 6f aa 6c 71 ae c4 f5 88 50 80 26 0f be 9d 24 ac | o.lq....P.&...$.
0x00000070: 4d fc a0 82 b3 b6 87 35 b3 d6 a8 35 cc 62 bd d5 | M......5...5.b..
$ crobe loadable crc ethernet_fcs example-patched.bin
example-patched.bin None <0x0:0x80>: 8eb2fbc8

We can compute effect of data change on CRC without having the whole binary:

\b
$ crobe crc patch ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d
To XOR on CRC: 34cf862a

Crobe may even do the XOR for you if you have old CRC:

\b
$ crobe crc patch ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --old ba7d7de2
To XOR on CRC: 34cf862a
Old CRC: ba7d7de2
New CRC: 8eb2fbc8

But this tool is also able to give you a bunch of bytes to change
at another offset in the payload in order to keep CRC intact.

Let's say we prefer to patch bytes at offset 0x60:

\b
$ crobe crc patch ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x60
To XOR on data at 0x60: 249ed2bf

Again, tool may calculate new data:

\b
$ crobe crc patch ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x60 --old 6faa6c71
To XOR on data at 0x60: 249ed2bf
Old data: 6faa6c71
New data: 4b34bece

And this actually works:

\b
$ crobe loadable to-bin example-patched.bin 4b34bece:literal:+0x60 example-fixed.bin
$ crobe loadable crc ethernet_fcs example-fixed.bin
example-fixed.bin None <0x0:0x80>: ba7d7de2

Patch offset may actually be before data offset:

\b
$ crobe crc patch ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x5 --old 6bb7775f
To XOR on data at 0x5: 247568f2
Old data: 6bb7775f
New data: 4fc21fad
$ crobe loadable to-bin example-patched.bin 4fc21fad:literal:+0x5 example-fixed.bin
$ crobe loadable crc ethernet_fcs example-fixed.bin
example-fixed.bin None <0x0:0x80>: ba7d7de2
"""
             )
@click.argument("alg", type = str)
@click.option("--patch-offset", type = base.HEX, default = None, help = "Offset for fixup data if not changing final CRC")
@click.option("--old", type = str, default = None, help = "Old CRC value (as payload bytes) or data before fixup patch", metavar = "HEX_DATA")
@click.argument("data_offset", type = base.HEX)
@click.argument("total_size", type = base.HEX)
@click.argument("old_data", type = str)
@click.argument("new_data", type = str)
def patch(alg, patch_offset, data_offset, total_size, old_data, new_data, old):
    """Give out bytes to XOR at CRC (or at a given offset in payload) to
    patch in order to keep CRC valid after changing some bytes.

    Change may be of arbitrary size, but patch to fix CRC must be of
    the CRC size.
    """
    crc_alg = Crc.from_desc_string(alg)
    old_data = bytes.fromhex(old_data)
    new_data = bytes.fromhex(new_data)
    if old is not None:
        old = bytes.fromhex(old)

    if patch_offset is not None:
        assert patch_offset < total_size - crc_alg.byte_width
        assert patch_offset + crc_alg.byte_width <= data_offset \
            or data_offset + len(new_data) <= patch_offset, \
            "Patch overlaps with data"

    assert len(old_data) == len(new_data)
    if old:
        assert len(old) == crc_alg.byte_width

    data_delta = xor_(old_data, new_data)

    if patch_offset is None:
        crc_xor_blob = crc_alg.data_mod_crc_delta_compute(
            data_offset, data_delta, total_size)

        print(f"To XOR on CRC: {crc_xor_blob.hex()}")

        if old:
            print(f"Old CRC: {old.hex()}")
            new_crc = xor_(old, crc_xor_blob)
            print(f"New CRC: {new_crc.hex()}")
    else:
        patch_xor_blob = crc_alg.data_mod_data_delta_compute(
            data_offset, data_delta, patch_offset)

        print(f"To XOR on data at {patch_offset:#x}: {patch_xor_blob.hex()}")

        if old:
            print(f"Old data: {old.hex()}")
            new_data = xor_(old, patch_xor_blob)
            print(f"New data: {new_data.hex()}")

def print_alg_info(alg):
    print(f"Calculation:")
    print(f"- Polynom representation: order 0 at {'LSB' if alg.order0_at_lsb else 'MSB'}")
    print(f"- Order: {alg.order}")
    print(f"- Divisor: {alg.poly:#x}")
    p = ' + '.join((f"x^{x}" if x else "1") for x in alg.poly_exponents)
    print(f"  Exponents: {p}")
    print(f"- Initial value: {alg.init:#x}")
    p = ' + '.join((f"x^{x}" if x else "1") for x in alg.init_exponents)
    print(f"  Exponents: {p or '0'}")
    print(f"Bitstream processing:")
    print(f"- Read bits in bytestream from", ["MSB", "LSB"][alg.pop_lsb], "of each byte")
    print(f"- Complement input data:", alg.complement_input)
    print(f"- Complement internal state:", alg.complement_state)
    print(f"Output generation:")
    print(f"- Bitswap output:", alg.spill_bitswap)
    print(f"- Byte order:", alg.spill_byte_order)
    print(f"Trivia:")
    print(f"- CRC state after blob with valid CRC: {alg.check_state:#x}")
    print(f"- CRC bytes of a blob with valid CRC: <{alg.as_bytes(alg.check_state).hex()}>")
    if alg.is_trinomial:
        print(f"- Is trinomial")
    if alg.is_prime:
        print(f"- Is prime")
    print("- Crobe short definition:", alg.info_string)
    aliases = alg.known_names
    if aliases:
        print("- Known as:", ', '.join(aliases))
    print("- Crobe instantiation:", repr(alg))
    print("- Reveng-like definition:", alg.reveng_string)
            
@crc.command()
@click.argument("alg", type = str, metavar = "ALG_NAME")
@click.option("--reciprocal", is_flag = True, help = "Use reciprocal of CRC")
def info(alg, reciprocal):
    """
    Print human-readable info about algorithm
    """
    alg = Crc.from_desc_string(alg)
    if reciprocal:
        alg = alg.reciprocal()
    print_alg_info(alg)

@crc.command()
@click.argument("poly", type = base.HEX, metavar = "POLY")
@click.argument("init", type = base.HEX, metavar = "INIT")
@click.option("--msb0", is_flag = True, help = "Order at MSB")
@click.option("--pop-msb", is_flag = True, help = "Pop bytestream from MSBs")
@click.option("--complement-state", is_flag = True, help = "Complement state")
@click.option("--complement-input", is_flag = True, help = "Complement input data")
@click.option("--spill-bitswap", is_flag = True, help = "Spill bitswap")
@click.option("--big-endian", is_flag = True, help = "Spill as Big-endian")
def build(poly, init, msb0, pop_msb, complement_state, complement_input,
          spill_bitswap, big_endian):
    """
    Build algorithm and print info
    """
    alg = Crc(poly = poly, init = init,
              order0_at_lsb = not msb0, pop_lsb = not pop_msb,
              complement_state = complement_state, complement_input = complement_input,
              spill_bitswap = spill_bitswap, spill_byte_order = "big" if big_endian else "little")
    print_alg_info(alg)

@crc.command(name = "list")
def list_():
    """
    List known CRCs
    """
    for name, alg in Crc.algorithms():
        print(f"{name}: {alg.info_string}")
