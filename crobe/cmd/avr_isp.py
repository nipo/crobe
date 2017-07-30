def main():
    from . import base
    from ..component.atmel.isp import Isp
    from ..component.atmel.atmega import Atmega
    import binascii

    class Tool(base.Freq):
        forced_interface = "spi"
        max_freq = 8e6

    args = Tool("AVR ISP test")
    spi = args.interface

    avr = Atmega(spi)

    spi.start()

    program = avr.program_mem_read(0, 0x4000)
    for i in range(0, len(program), 16):
        print("%04x %s" % (i, binascii.b2a_hex(program[i:i+16])))

if __name__ == '__main__':
    main()


