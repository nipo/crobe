from ..bitstring import BitString
import math
import time
from tqdm import tqdm
from crobe.target.pin_control import Mode

class Net:
    def __init__(self, *pins, shuffle = True):
        self.pins = list(pins)
        self.shuffle = shuffle

    def shift(self, i):
        if i and not self.shuffle:
            raise ValueError(i)
        if i >= len(self.pins):
            raise ValueError(i)
        return Net(*(self.pins[i:] + self.pins[:i]), shuffle = self.shuffle)

    @property
    def phases(self):
        if not self.shuffle:
            return 1
        return len(self.pins)

class TestPhase:
    def __init__(self, board, nets, constants):
        self.board = board

        scanned_pins = set()
        self.equipots = {}
        self.observers = set()
        self.drivers = {}
        self.constants = constants

        for net in nets:
            pins = set(net.pins)
            if scanned_pins & pins:
                raise ValueError("Some pins appear more than once", pins)

            driver = net.pins[0]
            observers = set(net.pins[1:])
            self.observers |= observers

            for o in observers:
                self.drivers[o] = driver
            
            self.equipots[driver] = observers

        w = math.ceil(math.log2(len(self.equipots)))
        self.pattern = {}
        self.rpattern = {}
        self.count = w * 2 + 2
        for i, d in enumerate(self.equipots.keys()):
            p = (2 << (w * 2)) | (i << w) | (~i & ((1 << w) - 1))
            self.pattern[d] = p
            self.rpattern[p] = d
        for a, pa in self.pattern.items():
            for b, pb in self.pattern.items():
                if a == b:
                    continue
                self.rpattern[pa & pb] = a+"&"+b
                self.rpattern[pa | pb] = a+"|"+b
        self.rpattern[0] = "GND"
        self.rpattern[(1 << self.count) - 1] = "VCC"

    def enable(self):
        for driver, observers in self.equipots.items():
            self.board.pin_config(driver, Mode.Pushpull)
            for obs in observers:
                self.board.pin_config(obs, Mode.Input)
        for pin, value in self.constants.items():
            self.board.pin_config(pin, Mode.Pushpull)
            self.board.pin_set(pin, value)

    def disable(self):
        for driver, observers in self.equipots.items():
            self.board.pin_config(driver, Mode.Input)
            for obs in observers:
                self.board.pin_config(obs, Mode.Input)
        for pin in self.constants.keys():
            self.board.pin_config(pin, Mode.Input)

    def scatter(self, pattern):
        for d in self.equipots.keys():
            self.board.pin_set(d, bool(self.pattern[d] & (1 << pattern)))

    def gather(self):
        effect = {}
        for driver, observers in self.equipots.items():
            values = self.board.pin_get_many(observers)
            for observer, value in values.items():
                effect[observer] = value
        return effect

    def test(self, pb = None):
        observed = dict((k, 0) for k in self.observers)

        self.enable()
        self.board.extest()

        for idx in range(self.count + 1):
            time.sleep(.01)
            if idx < self.count:
                self.scatter(idx)
            else:
                self.disable()
            self.board.extest()
            if pb:
                pb.update()
            if idx:
                for observer, value in self.gather().items():
                    observed[observer] |= int(bool(value)) << (idx - 1)

        ret = {}
        for observer, observed_pattern in observed.items():
            actual_driver = self.driver_by_pattern(observed_pattern)
            expected_driver = self.drivers[observer]
            expected_pattern = self.pattern[expected_driver]
            if actual_driver != expected_driver:
                ret[observer] = expected_driver, actual_driver, BitString(expected_pattern, self.count), BitString(observed_pattern, self.count)

        return ret

    def driver_by_pattern(self, pattern):
        return self.rpattern.get(int(pattern), None)
            
class BoardTester:
    def __init__(self, board, nets, constants):
        self.board = board
        self.nets = nets
        self.constants = constants
        
        phase_count = max((x.phases for x in nets), default = 0)
        self.phase = []
        for i in range(phase_count):
            phase_nets = []
            for net in nets:
                try:
                    n = net.shift(i)
                except ValueError:
                    continue
                phase_nets.append(n)
            self.phase.append(TestPhase(board, phase_nets, constants))

    def test(self):
        bad_observations = {}
        pb = tqdm(total = sum((p.count for p in self.phase), 0),
                  desc = "Boundary scan")

        for phase in self.phase:
            phase_bad_obs = phase.test(pb)

            for observer, data in phase_bad_obs.items():
                try:
                    bad_observations[observer].append(driver, data)
                except:
                    bad_observations[observer] = [data]
        return bad_observations
            
            
