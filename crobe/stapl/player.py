"""STAPL player for crobe JTAG hardware.

Implements StaplPlayer using a raw JTAG interface (not a Tap).
"""

import time

from ..bitstring import BitString
from .interpreter import StaplPlayer


class JtagPlayer(StaplPlayer):
    """StaplPlayer that drives hardware via a raw JTAG interface.

    Takes a JTAG interface (e.g. JtagMpsse) directly, NOT a Tap.
    The STAPL program handles its own IR/DR assembly with pre/post
    chain bypass padding.

    TAP state transitions are approximated via run-test/idle cycles
    (IRPAUSE, DRPAUSE mapped to IDLE).
    """

    def __init__(self, interface):
        self._iface = interface
        self._started = False

    def ir_scan(self, length, tdi, pre, post, capture):
        pre_bits, pre_data = pre
        post_bits, post_data = post

        combined = BitString()
        if pre_bits:
            combined.append(pre_data, pre_bits)
        combined.append(tdi, length)
        if post_bits:
            combined.append(post_data, post_bits)

        total = len(combined)

        if not self._started:
            self._iface.run(1)
            self._started = True
        self._iface.capture_ir()
        tdo = self._iface.shift(combined, read_tdo=capture)
        self._iface.run(1)

        if capture:
            tdo_all = bytes(tdo.data[:((total + 7) // 8)])
            tdo_bits = BitString(tdo_all, total)
            return bytes(tdo_bits[pre_bits:pre_bits + length])
        return None

    def dr_scan(self, length, tdi, pre, post, capture):
        pre_bits, pre_data = pre
        post_bits, post_data = post

        combined = BitString()
        if pre_bits:
            combined.append(pre_data, pre_bits)
        combined.append(tdi, length)
        if post_bits:
            combined.append(post_data, post_bits)

        total = len(combined)

        self._iface.capture_dr()
        tdo = self._iface.shift(combined, read_tdo=capture)
        self._iface.run(1)

        if capture:
            tdo_all = bytes(tdo.data[:((total + 7) // 8)])
            tdo_bits = BitString(tdo_all, total)
            return bytes(tdo_bits[pre_bits:pre_bits + length])
        return None

    def state(self, target, path=None):
        t = target.upper()
        if t == 'RESET':
            self._iface.run(5)
        else:
            self._iface.run(1)

    def wait(self, wait_state, cycles, usecs, end_state):
        if wait_state:
            self.state(wait_state)
        if cycles:
            self._iface.run(cycles)
        if usecs:
            time.sleep(usecs / 1_000_000)
        if end_state and end_state != wait_state:
            self.state(end_state)

    def trst(self, cycles, usecs):
        self._iface.run(5)

    def note(self, text):
        print(f"NOTE: {text}")

    def export(self, key, value):
        print(f"EXPORT {key} = {value}")
