def main():
    from . import base
    from ..svf.player import ChainPlayer, TapPlayer
    from ..svf.svf import SvfParser
    from ..protocol.jtag import Interface, Chain, Tap

    class Tool(base.Root, base.File):
        pass

    args = Tool("SVF player")

    svf = SvfParser(args.file)
    root = args.roots[0]
    
    if isinstance(root, Interface):
        root = root.children[0]

    if isinstance(root, Chain):
        player = ChainPlayer(root)
    elif isinstance(root, Tap):
        player = TapPlayer(root)
    else:
        print("Root %s is not a JTAG chain nor a TAP" % root)
        return

    player.run(svf)

if __name__ == '__main__':
    main()
