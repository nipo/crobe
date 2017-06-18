def main():
    from . import base
    from ..component.fpga.spartan6 import Spartan6

    class Tool(base.Speed, base.Programs):
        forced_interface = "jtag"
        program_count_needed = 1

    args = Tool("XC6S loader")

    args.interface.start()
    fpga, = args.interface.children_of_class(Spartan6)

    fpga.load(args.program)
    
if __name__ == '__main__':
    main()


