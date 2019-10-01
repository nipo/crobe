from ..bitstring import BitString
from ..bsdl.cache import Cache
from ..protocol import jtag
from ..target import pin_control
import time
import logging

class Pin:
    def __init__(self, board, offset, ic, oc, cc):
        self.board = board
        self.ic = ic
        self.oc = oc
        self.cc = cc
        self.ic_idx = ic.number + offset if ic else None
        self.oc_idx = oc.number + offset if oc else None
        self.cc_idx = cc.number + offset if cc else None

    @property
    def value(self):
        if self.ic_idx is None:
            raise RuntimeError("Pin has no input cell")
        return self.board.boundary_status[self.ic_idx]

    @value.setter
    def value(self, value):
        if self.oc_idx is None:
            raise RuntimeError("Pin has no output cell")
        self.board.boundary_control[self.oc_idx] = bool(value)

    def drive(self, drive):
        if self.cc_idx is None:
            raise RuntimeError("Pin has no inout control")
        if self.oc.disable_result != self.oc.DisableResult.Z:
            raise RuntimeError("Cannot make output Z")
        self.board.boundary_control[self.cc_idx] = drive ^ self.oc.disable_value

    def disable(self):
        if self.cc_idx is None:
            self.drive(False)
        if self.oc_idx is not None and self.oc.safe_bit is not None:
            self.board.boundary_control[self.oc_idx] = self.oc.safe_bit

class ChipInfo:
    def __init__(self, name, package):
        self.name = name
        self.package = package
        
class BoardController:
    """BoardController is a boundary scan controller for a board.  It can
    handle getting/setting pins for a complete board.

    Boundary scan register is supposed to be shifted in all chips at
    the same time, so this is what we do here. Then you may retrieve
    ChipControllers associated to each TAP through
    controller.chips[name], and control individual pins on them.

    """
    def __init__(self, chain, chip_info):
        assert isinstance(chain, jtag.Chain)
        self.chain = chain
        self.interface = chain.port

        cache = Cache.open()

        taps = chain.children[:]
        chips = {}

        self.ir_sample = BitString()
        self.ir_extest = BitString()
        boundary_len = 0

        for index, tap in enumerate(taps):
            try:
                info = chip_info[index]
            except:
                info = None

            if info is None:
                self.ir_sample += BitString(-1, tap.irlen)
                self.ir_extest += BitString(-1, tap.irlen)
                boundary_len += 1
                continue

            d = cache.filter(idcode = int(tap.idcode), package = info.package)

            if not d:
                raise ValueError("No BSDL entry for %s", tap.idcode)
            if len(d) > 1:
                raise KeyError("Ambiguity for part at index %d (%s), choose among packages: %s"
                               % (index, tap.idcode, ",".join(x.package_variant for x in d)))

            pc = ChipController(self, boundary_len, tap, d[0])
            chips[info.name] = pc

            self.ir_sample += pc.ir_sample
            self.ir_extest += pc.ir_extest
            boundary_len += pc.boundary_len

        self.ir_bypass = BitString(-1, len(self.ir_sample))
            
        self.chips = chips
        self.boundary_control = BitString(-1, boundary_len)

        self.disable()
        self.sample()

    def disable(self):
        for c in self.chips.values():
            c.disable()
        
    def sample(self):
        """
        Select sample and run it on all handled chips in chain.
        """
        self.__ir = self.ir_sample
        self.refresh()
        
    def extest(self):
        """
        Select extest and run it on all handled chips in chain.
        """
        self.__ir = self.ir_extest
        self.refresh()

    def bypass(self):
        """
        Unselect all
        """
        self.interface.execute([
            self.interface.cmd_capture_ir(),
            self.interface.cmd_shift(self.ir_bypass, read_tdo = False),
            self.interface.cmd_run(1),
            ])
        
    def refresh(self):
        """
        Run selected IR on all handled chips in chain.
        """
        shift_boundary = self.interface.cmd_shift(self.boundary_control, read_tdo = True)
        self.interface.execute([
            self.interface.cmd_capture_ir(),
            self.interface.cmd_shift(self.__ir, read_tdo = False),
            self.interface.cmd_run(1),
            self.interface.cmd_capture_dr(),
            shift_boundary,
            self.interface.cmd_run(1),
            ])
        self.boundary_status = shift_boundary.tdo

    def pin_get_all(self):
        """
        Retrieve all values for all pins from cache.
        Returns a dict, chip_name.pin_name as keys.
        """
        ret = {}
        for chip_name, chip in self.chips.items():
            for pin_name, value in chip.pin_get_all().items():
                ret[chip_name+"."+pin_name] = value
        return ret

    def pin_get_many(self, pin_names = []):
        to_get = dict((c, set()) for c in self.chips.keys())
        for n in pin_names:
            chip_name, pin_name = n.split(".", 1)
            to_get[chip_name].add(pin_name)
        ret = {}
        for chip_name, pins in to_get.items():
            pin_values = self.chips[chip_name].pin_get_many(pins)
            for pin, value in pin_values.items():
                ret[chip_name+'.'+pin] = value
        return ret

    def pin_get(self, name):
        chip_name, pin_name = name.split(".", 1)
        return self.chips[chip_name].pin_get(pin_name)

    def pin_set(self, name, value):
        chip_name, pin_name = name.split(".", 1)
        return self.chips[chip_name].pin_set(pin_name, value)

    def pin_config(self, name, mode = pin_control.Mode.Input):
        chip_name, pin_name = name.split(".", 1)
        return self.chips[chip_name].pin_config(pin_name, mode)

    @classmethod
    def differences(cls, before, after):
        """
        Compare two outputs of pin_get_all()
        """
        changed = {}

        for pin in sorted(before):
            b = before[pin]
            a = after[pin]

            if b != a:
                changed[pin] = a

        return changed

class ChipController:
    """This controller can read/write status of pins in a given chip. It
    works on BoardController's cached version of the global boundary
    register.
    """
    def __init__(self, board, boundary_offset, tap, definition):
        self.board = board
        self.definition = definition
        self.boundary_offset = boundary_offset
        self.tap = tap

        self.ir_sample = BitString(definition.instructions['sample'].opcodes[0].value,
                                   definition.ir_length)
        self.ir_preload = BitString(definition.instructions['preload'].opcodes[0].value,
                                   definition.ir_length)
        self.ir_extest = BitString(definition.instructions['extest'].opcodes[0].value,
                                   definition.ir_length)
        self.boundary_len = definition.registers["boundary"].length

        self.__pins = {}
        
        for p in sorted(self.definition.pins.values()):
            if p.index is not None:
                name = "%s_%d" % (p.name, p.index)
            else:
                name = p.name

            input_cell = self.definition.pin_input_cell.get(p)
            output_cell = self.definition.pin_output_cell.get(p)
            control_cell = self.definition.pin_control_cell.get(p)

            if not (input_cell or output_cell or control_cell):
                continue

            self.__pins[name] = Pin(board, boundary_offset, input_cell, output_cell, control_cell)

    def disable(self):
        for c in self.definition.boundary:
            if c.disable_value is not None:
                self.board.boundary_control[self.boundary_offset + c.number] = c.disable_value
            elif c.safe_bit is not None:
                self.board.boundary_control[self.boundary_offset + c.number] = c.safe_bit
            
    def pin_get_all(self):
        ret = {}
        for pin_name, pin in self.__pins.items():
            if not pin.ic:
                continue
            ret[pin_name] = pin.value
        return ret

    @property
    def pin_names(self):
        return list(self.__pins.keys())

    def pin_get_many(self, pin_names = []):
        ret = {}
        for n in pin_names:
            ret[n] = self.__pins[n].value
        return ret

    def pin_get(self, name):
        return self.__pins[name].value

    def pin_set(self, name, value):
        self.__pins[name].value = value

    def pin_config(self, name, mode = pin_control.Mode.Input):
        if mode in [pin_control.Mode.Disabled, pin_control.Mode.Input]:
            self.__pins[name].drive(False)
        elif mode == pin_control.Mode.Pushpull:
            self.__pins[name].drive(True)
        else:
            raise ValueError("Cannot use mode %s" % mode)
    
class PinController(pin_control.Controller):
    def __init__(self, chip_controller):
        self.chip_controller = chip_controller

    @property
    def pin_names(self):
        return chip_controller.pin_names

    def pin_get_many(self, pin_names = []):
        self.chip_controller.board.refresh()
        return self.chip_controller.pin_get_many(pin_names)

    def pin_get(self, name):
        self.chip_controller.board.refresh()
        return self.chip_controller.pin_get(name)

    def pin_set(self, name, value):
        self.chip_controller.pin_set(name, value)
        self.chip_controller.board.refresh()

    def pin_config(self, name, mode = pin_control.Mode.Input):
        self.chip_controller.pin_config(name, mode)
        self.chip_controller.board.refresh()
