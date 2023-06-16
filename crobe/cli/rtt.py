from . import base
import click
from ..util.file_monitor import FileMonitorThread
from ..loadable.model import Program

@base.cli.group(help = "RTT utilities")
def rtt():
    pass

class AutoUpdater(FileMonitorThread):
    def __init__(self, path, target, rtt_pipe_console, rtt_control_symbol_name = None):
        self.target = target
        super().__init__(path)
        self.rtt_pipe_console = rtt_pipe_console
        self.rtt_control_symbol_name = rtt_control_symbol_name

    def on_disappear(self):
        print(f"{self.path} disappeared")

    def on_appear(self):
        print(f"{self.path} appeared, reloading")
        self.reload()

    def on_update(self):
        print(f"{self.path} changed, reloading")
        self.reload()

    def reload(self):
        try:
            program = Program.from_file(self.path)
        except Exception as e:
            print(f"Unable to load {self.path}, will retry when it changes again")
            return

        if self.rtt_pipe_console:
            self.rtt_pipe_console.address_set(None)

        for retry in range(3, -1, -1):
            try:
                self.target.write(program,
                                  do_erase = False,
                                  do_verify = False,
                                  do_start = True)

                self.target.run_attached()
                break
            except:
                if retry:
                    continue
                raise

        if self.rtt_control_symbol_name:
            try:
                addr = program.symbol_address_get(self.rtt_control_symbol_name)
            except:
                addr = None

            if not addr:
                print(f"RTT control {self.rtt_control_symbol_name} not found in {self.path}")
                return
            
            print(f"RTT control {self.rtt_control_symbol_name} at {addr:#010x}")
            if self.rtt_pipe_console:
                self.rtt_pipe_console.address_set(addr)
        
@rtt.command(help = "Console on RTT, optionally autorefresh binary")
@click.option('-r', '--roots', type = base.ROOT, multiple = True)
@base.field()
@click.option('--target', '-t', metavar = 'CRIT', help = 'Target criterion', default = "0")
@click.option("--address", type = str, default = None, help = "RTT control block address (may be a 'begin:end' range)")
@click.option("--symbol", type = str, default = "rtt_control", help = "RTT control block symbol name in binary")
@click.option('-p', '--program', type = click.Path(exists = True, dir_okay = False), default = None)
def console(roots, field, target, program, address, symbol):
    from ..util.console import PipeConsole
    from ..target.model import Target

    target = field.child_summon(target)
    target.start()
    rtt = target.child_summon("rtt")
    rtt.start()

    if address is not None:
        rtt.address_set(address)

    channel0 = rtt.child_summon("channel0")
        
    console = PipeConsole(channel0)
    console.start()

    autoupdater = AutoUpdater(program, target, rtt, symbol)
    autoupdater.start()

    autoupdater.join()
    console.join()
