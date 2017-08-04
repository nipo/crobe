def main():
    from . import base
    from ..svf.player import Player
    from ..svf.svf import SvfParser
    from ..adapter.protocol.jtag import Interface

    class Tool(base.Root, base.File):
        expected_root = Interface

    args = Tool("SVF player")

    svf = SvfParser(args.file)
    player = Player(svf, args.root)

    player.run()

if __name__ == '__main__':
    main()
