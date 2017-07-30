def main():
    from . import base
    from ..component.xilinx.spartan6 import Spartan6

    class Tool(base.Freq, base.Programs):
        forced_interface = "jtag"
        program_count_needed = 1
        max_freq = 50e6

    args = Tool("XC6S loader")

    args.interface.start()
    fpga, = args.interface.children_of_class(Spartan6)

    fpga.load(args.program)
    
if __name__ == '__main__':
    main()


