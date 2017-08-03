from .. import base
from ...adapter.jlink import Adapter
from ...component.energy_micro.stk import *
import colorama
import time

class EnergyDisplay:
    frame = 10e-6
    SLOW = 1e-2 / frame
    FAST = 1e-4 / frame
    FAST_TO_SLOW = SLOW / FAST

    def __init__(self, colored = True):
        self.colored = colored

        self.lowpass_slow = 0.
        self.lowpass_fast = 0.
        self.noise_lowpass = 0.
        self.time_origin = time.time()
        self.last_rx = self.time_origin
        self.since_last_change = 0.
        self.sum_since_last_change = 0
        self.count_since_last_change = 0
        self.last_conso = 0
        self.state = "\r"
        self.sample_date = 0
        self.line_date = 0
        self.last_conso_str = ""
        self.packet_time_lowpass = 0.

    def exponent(self, x, unit, colors = True):
        end = colorama.Style.RESET_ALL
        for mult, suf, color, last in [(1e-3, "k", colorama.Fore.RED, False),
                                       (1, " ", colorama.Fore.MAGENTA, False),
                                       (1e3, "m", colorama.Fore.YELLOW, False),
                                       (1e6, "u", colorama.Fore.GREEN, False),
                                       (1e9, "n", colorama.Fore.CYAN, True)]:
            mant = x * mult
            if mant >= 1 or last:
                if not self.colored or not colors:
                    color = ""
                    end = ""
                return color + ("%.1f %c%s" % (mant, suf, unit)).rjust(8, " ") + end
        return "  0.   " + unit
    
    def new_data(self, voltage, current):
        now = time.time()
        self.packet_time_lowpass += (now - self.last_rx) - self.packet_time_lowpass / self.FAST
        self.last_rx = now
        sample_time = self.packet_time_lowpass / self.FAST / 256.

        for sample in current:
            self.lowpass_slow += sample - self.lowpass_slow / self.SLOW
            self.lowpass_fast += sample - self.lowpass_fast / self.FAST
            self.noise_lowpass += abs(sample - self.lowpass_slow / self.SLOW) - self.noise_lowpass / self.SLOW

            if abs(sample - self.lowpass_fast / self.FAST) > self.noise_lowpass / self.SLOW * 10 \
               and self.count_since_last_change:
                conso = self.sum_since_last_change / self.count_since_last_change
                conso_str = self.exponent(conso, "A")
                if conso_str != self.last_conso_str:
                    if self.last_conso > conso:
                        print("\x1b[2K\r %8.3f %s" % (self.line_date, self.state), flush = True)
                        self.state = ""
                        self.line_date = self.sample_date
                    self.state += "  %s %s;" % (self.exponent(self.since_last_change, "s", colors = False),
                                           conso_str)
                    self.since_last_change = 0.
                    self.sum_since_last_change = 0.
                    self.count_since_last_change = 0
                    self.last_conso = conso
                    self.last_conso_str = conso_str

            if self.count_since_last_change:
                conso = self.sum_since_last_change / self.count_since_last_change
                conso_str = self.exponent(conso, "A")
                if self.last_conso > conso and self.state and conso_str != self.last_conso_str:
                    print("\x1b[2K\r %8.3f %s" % (self.line_date, self.state), flush = True)
                    self.state = ""
                    self.line_date = self.sample_date
                if (self.count_since_last_change & 0xff) == 0:
                    print("\x1b[2K\r %8.3f" % self.line_date, self.state,
                          " %s %s;" % (self.exponent(self.since_last_change, "s", colors = False), conso_str),
                          end = '', flush = True)
                self.last_conso_str = conso_str

            self.sum_since_last_change += sample
            self.count_since_last_change += 1
            self.since_last_change += sample_time

        self.sample_date = now - self.time_origin
        
def main():
    class Tool(base.Root):
        def c20_mode_declare(self):
            self.parser.add_argument("mode", metavar = "MODE",
                                     type = str, default = "",
                                     nargs = "?",
                                     help = "MCU mode")

        def c20_mode_parse(self, args):
            self.mode = args.mode

    args = Tool("EFM32 STK debug mode tool")

    jlink = args.root
    assert isinstance(jlink, Adapter)

    for i in jlink.supported_interfaces:
        try:
            interface = jlink.open(i)
        except NotImplementedError:
            continue

        stk = EfmStk(interface)

        display = EnergyDisplay()

        monitor = stk.energy_monitor(display.new_data)

        try:
            monitor.join()
        except KeyboardInterrupt:
            monitor.stop()
            monitor.join()
            print()
        
if __name__ == '__main__':
    main()


