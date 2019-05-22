import click
from ...cli import base
from .bitstream import Bitstream
from .parts import PARTS
from ...util.endian import bitswap8
from ...loadable.object import Program

@click.group()
def cli():
    pass

@cli.command(help = "Save bitstream as C header")
@click.argument("program", type = click.Path(dir_okay = False), nargs = -1)
@click.argument("header", type = click.File("w"))
@click.option("--variable-name", default = "bitstream", help = "C Variable name")
@click.option("--msb-first", is_flag = True)
def to_c_header(program, header, variable_name, msb_first):
    bs = Bitstream(PARTS, Program.from_file(program[0]))
    header.write("#ifndef %s_BITSTREAM_H_\n" % variable_name.upper())
    header.write("#define %s_BITSTREAM_H_\n" % variable_name.upper())
    header.write("\n")
    header.write("// Data to send in array order, %s first.\n" % ("MSB" if msb_first else "LSB"))
    header.write("\n")
    header.write("static const size_t %s_col_bit_count = %d;\n" % (variable_name, bs.info.col_bit_count))
    header.write("static const size_t %s_row_count = %d;\n" % (variable_name, bs.info.row_count))
    header.write("static const size_t %s_row_stride = %d;\n" % (variable_name, len(bs.rti[0].data)))
    header.write("static const uint8_t %s[%d*%d] = {" % (variable_name, len(bs.rti[0].data), len(bs.rti)))
    for rn, frame in enumerate(bs.rti):
        fd = frame.data
        if not msb_first:
            fd = bitswap8(fd)
        
        header.write("\n // Row %d" % rn)
        for i, b in enumerate(fd):
            if i % 16 == 0:
                header.write("\n")
            header.write(" 0x%02x," % b)
                
    header.write("};\n")
    header.write("\n")
    header.write("#endif\n")

if __name__ == "__main__":
    cli.main()
