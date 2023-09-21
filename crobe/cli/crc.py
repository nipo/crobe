from . import base
from ..util.crc import Crc
import click

@base.cli.group(help = "CRC tools")
def crc():
    pass

@crc.command()
@click.argument("data", type = str)
@click.option("--alg", type = str)
def init_recover(data, alg):
    """
    Assuming a blob with correct CRC appended, recover initial value
    """
    crc_alg = getattr(Crc, alg)
    data = bytes.fromhex(data)
    init_state = crc_alg._backward_bytes(crc_alg.check_state, data)
    print(f"{init_state:x}")

@crc.command()
@click.argument("data", type = str)
@click.option("--init", type = base.HEX, default = None)
@click.option("--alg", type = str)
def calculate(data, alg, init):
    """
    Calculate CRC of a small blob
    """
    crc_alg = getattr(Crc, alg)
    data = bytes.fromhex(data)
    state = crc_alg(init)
    state.update(data)
    print(f"State: {state.state:#x}")
    print(f"Output as integer: {int(state):#x}")
    print(f"Output as bytes:   {bytes(state).hex()}")

@crc.command()
@click.argument("data", type = str)
@click.option("--init", type = base.HEX, default = None)
@click.option("--alg", type = str)
def validate(data, alg, init):
    """
    Check a piece of data passes CRC validation
    """
    crc_alg = getattr(Crc, alg)
    data = bytes.fromhex(data)
    state = crc_alg(init)
    state.update(data)
    if not state.is_valid():
        raise click.exceptions.Exit(1)

@crc.command()
@click.argument("data", type = str)
@click.argument("output", type = str)
@click.option("--width", type = int)
@click.option("--init", type = base.HEX)
@click.option("--poly", type = base.HEX)
@click.option("--swap4", is_flag = True)
@click.option("--c-alg", is_flag = True)
def find_parameters(data, output, width, poly, init, swap4, c_alg):
    """
    Find back parameters of CRC
    """
    from crobe.util.endian import swib, swap

    c_alg_test = True

    try:
        data = bytes.fromhex(data)
    except ValueError:
        from ..loadable.model import Program
        p = Program.from_file(data)
        data = p[0].data
        c_alg_test = False

    value_bytes = bytes.fromhex(output)
    value = int.from_bytes(value_bytes, "little")
        
    if swap4:
        data = b"".join(data[i:i+4][::-1] for i in range(0, len(data), 4))
        c_alg_test = False
        
    mask = (1 << width) - 1
    outputs = [value]
    outputs += [swap(i, width) for i in outputs]
    outputs += [swib(i, width) for i in outputs]
    outputs += [i ^ mask for i in outputs]
    inits = [init]
    inits += [swap(i, width) for i in inits]
    inits += [swib(i, width) for i in inits]
    inits += [i ^ mask for i in inits]

    matching = set()
        
    for _poly in [poly, swib(poly, width)]:
        for pop_lsb in [False, True]:
            for insert_msb in [False, True]:
                for complement_input in [False, True]:
                    crc_alg = Crc(
                        init = 0,
                        complement_state = False,
                        spill_bitswap = False,
                        spill_byte_order = "little",

                        width = width,
                        poly = _poly,
                        pop_lsb = pop_lsb,
                        insert_msb = insert_msb,
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

    for crc_alg in ok:
        print(repr(crc_alg))

        if c_alg:
            print("#include <assert.h>")
            print("#include <stdio.h>")
            print("#include <stdlib.h>")
            print("#include <stdint.h>")
            crc_alg.c_bit_spill()
            if c_alg_test:
                crc_alg.c_test_spill(data)

@crc.command(short_help = "Compute CRC or data patch after modification in a blob")
@click.option("--alg", type = str, help = "CRC algorithm name", metavar = "ALG_NAME")
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
    $ crobe loadable crc --alg ethernet_fcs example.bin
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
    $ crobe loadable crc --alg ethernet_fcs example-patched.bin                       
    example-patched.bin None <0x0:0x80>: 8eb2fbc8

    We can compute effect of data change on CRC without having the whole binary:

    \b
    $ crobe crc patch --alg ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d
    To XOR on CRC: 34cf862a

    Crobe may even do the XOR for you if you have old CRC:

    \b
    $ crobe crc patch --alg ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --old ba7d7de2 
    To XOR on CRC: 34cf862a
    Old CRC: ba7d7de2
    New CRC: 8eb2fbc8

    But this tool is also able to give you a bunch of bytes to change
    at another offset in the payload in order to keep CRC intact.

    Let's say we prefer to patch bytes at offset 0x60:

    \b
    $ crobe crc patch --alg ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x60
    To XOR on data at 0x60: 249ed2bf

    Again, tool may calculate new data:

    \b
    $ crobe crc patch --alg ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x60 --old 6faa6c71   
    To XOR on data at 0x60: 249ed2bf
    Old data: 6faa6c71
    New data: 4b34bece

    And this actually works:

    \b
    $ crobe loadable to-bin example-patched.bin 4b34bece:literal:+0x60 example-fixed.bin
    $ crobe loadable crc --alg ethernet_fcs example-fixed.bin                           
    example-fixed.bin None <0x0:0x80>: ba7d7de2

    Patch offset may actually be before data offset:
    
    \b
    $ crobe crc patch --alg ethernet_fcs 0x40 0x80 e5be4660861c c0dedeadf00d --patch-offset 0x5 --old 6bb7775f
    To XOR on data at 0x5: 247568f2
    Old data: 6bb7775f
    New data: 4fc21fad
    $ crobe loadable to-bin example-patched.bin 4fc21fad:literal:+0x5 example-fixed.bin
    $ crobe loadable crc --alg ethernet_fcs example-fixed.bin
    example-fixed.bin None <0x0:0x80>: ba7d7de2

    """
    crc_alg = getattr(Crc, alg)
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

    data_delta = bytes([(a^b) for (a,b) in zip(old_data, new_data)])
    data_delta_contribution = crc_alg._forward_bytes(0, data_delta)

    if patch_offset is None:
        crc_xor_blob = crc_alg.data_mod_data_delta_compute(
            data_offset, old_data, new_data, total_size)

        print(f"To XOR on CRC: {crc_xor_blob.hex()}")

        if old:
            print(f"Old CRC: {old.hex()}")
            new_crc = bytes([(a^b) for (a,b) in zip(old, crc_xor_blob)])
            print(f"New CRC: {new_crc.hex()}")
    else:
        patch_xor_blob = crc_alg.data_mod_data_delta_compute(
            data_offset, old_data, new_data, patch_offset)

        print(f"To XOR on data at {patch_offset:#x}: {patch_xor_blob.hex()}")

        if old:
            print(f"Old data: {old.hex()}")
            new_data = bytes([(a^b) for (a,b) in zip(old, patch_xor_blob)])
            print(f"New data: {new_data.hex()}")
