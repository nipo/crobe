from ....model import PortComponent
from ....protocol import base

class Dacx0508SlopeController(PortComponent):
    # All arguments are big-endian
    CMD_CURRENT_SET   = 0x00 # 3 LSB = channel, 2 bytes current value follows
    CMD_TARGET_SET    = 0x08 # 2 bytes target value follows
    CMD_INCREMENT_SET = 0x09 # 4 bytes increment value follows

    def __init__(self, port, name = "dacx0508_slope", clock_freq = 50e6):
        super().__init__(port, name)
        self.clock_freq = clock_freq

    def cmd_current_set(self, channel, value):
        channel = int(channel) & 7
        value = int(value) & 0xffff
        return bytes([self.CMD_CURRENT_SET | channel]) + value.to_bytes(2, "big")

    def cmd_target_set(self, target):
        target = int(target) & 0xffff
        return bytes([self.CMD_TARGET_SET]) + target.to_bytes(2, "big")

    def cmd_increment_set(self, increment):
        increment = int(increment * 2 ** 16) & 0xffffffff
        assert(increment & 0xffff)
        return bytes([self.CMD_INCREMENT_SET]) + increment.to_bytes(4, "big")

    def init(self, channel, value):
        self.port.send_receive(self.cmd_current_set(channel, value))

    def slope_set(self, unit_per_sec):
        """
        Sets target slope, in max DAC LSB per second.
        """
        increment = unit_per_sec / self.clock_freq
        self.port.send_receive(self.cmd_increment_set(increment))

    def target_set(self, target):
        self.port.send_receive(self.cmd_target_set(target))
