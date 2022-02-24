from ..bitstring import BitString
from ..protocol import jtag, bitbang
from ..bsdl.cache import Cache
from ..bscan.controller import ChipController
from ..util.pretty import metric

class IoInfo(bitbang.IoInfo):
    def __init__(self, name, pin):
        self.name = name
        self.pin = pin
        self.mode = None
        self.output = None

        self.supported_modes = 0
        if pin.ic_idx is not None:
            self.supported_modes |= bitbang.Mode.Input
        if pin.oc_idx is not None:
            if pin.cc_idx is not None:
                self.supported_modes |= bitbang.Mode.D0 | bitbang.Mode.D1
            else:
                self.supported_modes |= bitbang.Mode.D0 | bitbang.Mode.D1

    def set(self, mode = None, value = None):
        if mode is not None:
            self.mode = mode & self.supported_modes
        if value is not None:
            self.output = value
                
    def bs_scatter(self):
        if (self.mode & bitbang.Mode.D1) and self.output:
            self.pin.value = True
            self.pin.drive(True)
        elif (self.mode & bitbang.Mode.D0) and not self.output:
            self.pin.value = False
            self.pin.drive(True)
        else:
            self.pin.value = False
            self.pin.drive(False)
            
@jtag.Tap.db.register("bb")
class TapBitbang(bitbang.Interface):
    cache = None

    @classmethod
    def _cache_init(cls):
        if cls.cache is not None:
            return
        cls.cache = Cache.open()
        
    def __init__(self, tap):
        self.controller = None
        self.padding_cycles = 1
        super().__init__(tap, "bb")
        self.package = None

    def freq_update(self, freq):
        if not self.controller:
            return 100e6

        freq = float(freq)
        slot_cycles = self.controller.boundary_len + 10
        jtag_freq = self.port.port.port.freq
        target_slot_cycles = jtag_freq / freq
        self.padding_cycles = int(max(1, target_slot_cycles - slot_cycles))
        new_freq = jtag_freq / (slot_cycles + self.padding_cycles)

        self.logger.trace("Now inserting %d run cycles over boundary len of %d for capping freq to %s from JTAG freq of %s",
                         self.padding_cycles,
                         self.controller.boundary_len,
                         metric(new_freq, "Hz"),
                         metric(jtag_freq, "Hz"))
        return new_freq

    def option_set(self, opt):
        try:
            k, v = opt.split("=", 1)
        except ValueError:
            return super().option_set(opt)

        if k in ["package", "pkg"]:
            self.package = v
            return

        return super().option_set(opt)

    def start(self):
        self._cache_init()

        d = self.cache.filter(idcode = int(self.port.idcode or 0), package = self.package)

        if not d:
            raise ValueError("No BSDL entry for %s in package %s", self.port.idcode, self.package)

        if len(d) > 1:
            raise KeyError("Ambiguity for package, choose among: %s"
                           % (", ".join(x.package_variant for x in d)))

        self.definition = d[0]
        
        self.controller = ChipController(self, 0, self.port, self.definition)
        self.boundary_control = BitString(-1, self.controller.boundary_len)
        self.boundary_status = BitString(-1, self.controller.boundary_len)

        self.pins = {}
        for name, pin in self.controller.pins.items():
            name = name.lower()
            self.pins[name] = IoInfo(name, pin)

        self.controller.disable()
        self.scanned_once = False

    def execute(self, operation_list):
        ops = list(operation_list)
        cmds = []
        pending = {}

        if not self.scanned_once:
            cmds.append(self.port.cmd_dr_shift(
                ir = self.controller.ir_preload,
                dr = self.boundary_control,
                read_tdo = False))
            self.scanned_once = True

        for index, op in enumerate(ops):
            read = False
            if isinstance(op, bitbang.IoSet):
                for iop in op.ops:
                    io = self.pins[iop.io]
                    io.set(mode = iop.mode, value = iop.value)
                    io.bs_scatter()
            elif isinstance(op, bitbang.IoGet):
                pending[index] = len(cmds)
                read = True

            else:
                raise base.ProtocolError("Unknown Bitbang operation %s" % type(op))

            cmds.append(self.port.cmd_dr_shift(ir = self.controller.ir_extest,
                                               dr = self.boundary_control,
                                               read_tdo = read,
                                               return_type = BitString))

            cmds.append(self.port.cmd_run(self.padding_cycles))

        self.port.execute(cmds)

        for index, op in enumerate(ops):
            if isinstance(op, bitbang.IoGet):
                cmd_idx = pending[index]
                self.boundary_status = cmds[cmd_idx].tdo
                op.values = self.controller.pin_get_many(op.ios)

    def io_info(self):
        return self.pins
