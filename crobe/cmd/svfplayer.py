def main():
    from . import base
    from ..svf.player import Player
    from ..svf.svf import SvfParser

    class Tool(base.Speed, base.File):
        forced_interface = "jtag"

    args = Tool("SVF player")

    args.interface.start()

    svf = SvfParser(args.file)
    player = Player(svf, args.interface)

    player.run()

if __name__ == '__main__':
    main()
