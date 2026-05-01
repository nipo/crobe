from . import base
import click


@base.cli.group(help="Altera/Intel-specific")
def altera():
    pass


@altera.command(name="jop-server",
                help="Expose a JTAG interface as an Altera JoP "
                     "(JTAG-over-Protocol) server for Quartus / "
                     "SignalTap / system-console")
@click.option("-r", "--root", type=base.ROOT, required=True,
              help="JTAG interface root (e.g. -r [adapter]/jtag)")
@click.option("-p", "--port", type=int, default=1259,
              help="TCP port to listen on (default 1259, the Altera "
                   "etherlink default)")
@click.option("-H", "--host", type=str, default="::",
              help="Bind address (default :: — IPv6 + v4-mapped)")
@click.option("--mgmt", "mgmt_support", is_flag=True, default=False,
              help="Advertise MGMT_SUPPORT=1 in the welcome banner. "
                   "Default off — we don't decode the MGMT side-channel "
                   "yet, and Quartus skips it when MGMT_SUPPORT=0.")
def jop_server(root, port, host, mgmt_support):
    from ..protocol.jtag import Interface
    from ..jop.listener import JopListener

    if not isinstance(root, Interface):
        raise click.ClickException(
            f"{type(root).__name__} is not a JTAG interface — "
            f"try -r [adapter]/jtag")

    try:
        root.reset = False
    except (NotImplementedError, AttributeError):
        pass

    listener = JopListener(root, host=host, port=port,
                           mgmt_support=mgmt_support)
    click.echo(f"JoP server on [{host}]:{port}")
    listener.serve_forever()
