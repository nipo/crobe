from . import base
import click

@base.cli.group()
def mpm54304():
    "MPM54304-specific"

@mpm54304.command()
@click.option('-r', '--root', type = base.ROOT)
def dump(root):
    """Read and print the full register configuration (all 4 bucks + system regs)"""

    from ..component.mps.mpm54304 import Mpm54304

    assert isinstance(root, Mpm54304)

    root.dump_configuration()

@mpm54304.command(name = "set-vout")
@click.option('-r', '--root', type = base.ROOT)
@click.option('--vout1', type = float, default = None, help = "Buck 1 output voltage, V")
@click.option('--vout2', type = float, default = None, help = "Buck 2 output voltage, V")
@click.option('--vout3', type = float, default = None, help = "Buck 3 output voltage, V")
@click.option('--vout4', type = float, default = None, help = "Buck 4 output voltage, V")
@click.option('--dry-run', is_flag = True, help = "Compute and print register values without writing them")
def set_vout(root, vout1, vout2, vout3, vout4, dry_run):
    """Configure buck output voltages over I2C.

    Only channels given a value are touched. Each accepts 0.55-1.82V
    (direct feedback, 10mV steps) or 1.65-5.46V (internal /3 divider,
    30mV steps at the output); direct mode is used whenever a value
    falls in the overlap.

    Example:

        crobe mpm54304 set-vout -r .../mpm54304(saddr=0x68) --vout1 1.2 --vout4 3.3

    This writes the I2C registers only (takes effect immediately, and
    survives EN toggling) -- it is NOT burned into MTP, so a VIN
    power-cycle reloads the last MTP-programmed configuration.
    """

    from ..component.mps.mpm54304 import Mpm54304

    assert isinstance(root, Mpm54304)

    requested = {1: vout1, 2: vout2, 3: vout3, 4: vout4}
    requested = {buck: v for buck, v in requested.items() if v is not None}

    if not requested:
        print("Nothing to do: pass at least one of --vout1/--vout2/--vout3/--vout4")
        return

    for buck, voltage in sorted(requested.items()):
        reg = root.compute_vout_reg(buck, voltage)
        actual = reg.vref * (3 if reg.vout_select else 1)
        addr = root._VOUT_REG_ADDR[buck]
        print("Buck%d: %.3fV requested -> vout_select=%d vref=%.3fV -> %.3fV actual (reg 0x%02x = 0x%02x)"
              % (buck, voltage, reg.vout_select, reg.vref, actual, addr, int(reg)))

        if not dry_run:
            root.reg_write(reg)

    if not dry_run:
        print("\nWritten to I2C registers (volatile: lost on the next VIN power-up unless MTP-burned).")

@mpm54304.command(name = "mtp-program")
@click.option('-r', '--root', type = base.ROOT)
@click.option('--yes', is_flag = True, help = "Skip the interactive confirmation prompt")
def mtp_program(root, yes):
    """Burn the CURRENT I2C register configuration into MTP -- PERMANENT.

    MTP is two-time programmable. If current_mtp_page_index already
    reads PAGE3 (see 'dump'), this chip has used both of its burns and
    this command will not do anything further to it.

    Make sure VIN has comfortable margin above the datasheet's 5.1V
    minimum for the duration of the burn, and review the printed
    configuration below carefully before confirming -- everything in
    registers 0x00-0x13 gets burned as one block, not just whatever you
    meant to change.
    """

    from ..component.mps.mpm54304 import Mpm54304

    assert isinstance(root, Mpm54304)

    print("Configuration about to be burned:\n")
    root.dump_configuration()

    if not yes:
        click.confirm(
            "This is a PERMANENT, irreversible MTP burn. Proceed?", abort = True)

    print("Burning MTP...")
    status = root.burn_mtp()
    print("Done. MTP page is now: %s (checksum_flag=%s)"
          % (status.current_mtp_page_index, status.checksum_flag))

    print("\nVerifying by re-reading the full configuration:\n")
    root.dump_configuration()
