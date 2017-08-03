def main():
    from . import base
    from ..svf.player import Player
    from ..svf.svf import SvfParser

    class Tool(base.Root, base.File):
        forced_interface = "jtag"

    args = Tool("SVF player")

    svf = SvfParser(args.file)
    player = Player(svf, args.root)

    player.run()

if __name__ == '__main__':
    main()
