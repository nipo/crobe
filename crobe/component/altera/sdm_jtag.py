"""SDM transport over JTAG.

Implements SDM frame I/O using the TAP's SDM_CMD and SDM_RSP
instructions. These must be defined on the Tap class as:

    SDM_CMD = Instruction(0x201, None)
    SDM_RSP = Instruction(0x202, None)

34-bit DR format:
  CMD (TDI): [31:0] = word, [33:32] = framing
             00=idle, 01=more, 10=last, 11=single
  RSP (TDO): [1:0] = framing, [33:2] = word
             00=idle, 01=more, 11=last
"""

import time
from ...bitstring import BitString
from .sdm import Sdm, TimeoutError
import random
import enum

class CmdFraming(enum.IntEnum):
    """CMD framing values [33:32]"""
    IDLE = 0
    MORE = 1
    LAST = 2
    INVAL = 3

class RspFraming(enum.IntEnum):
    """2RSP framing values [1:0]"""
    IDLE = 0
    MORE = 1
    INVAL = 2
    LAST = 3

# Max words per batch (limits how many shifts we post before awaiting)
_BATCH_SIZE = 64


class SdmJtag(Sdm):
    """SDM transport over JTAG SDM_CMD/SDM_RSP instructions.

    Takes a Tap instance that must define SDM_CMD and SDM_RSP
    instructions.
    """

    def __init__(self, tap):
        super().__init__(tap)
        assert hasattr(tap, 'SDM_CMD'), "Tap must define SDM_CMD instruction"
        assert hasattr(tap, 'SDM_RSP'), "Tap must define SDM_RSP instruction"
        assert hasattr(tap, 'SDM_WAKEUP'), "Tap must define SDM_WAKEUP instruction"

    # ------------------------------------------------------------------
    # Packing
    # ------------------------------------------------------------------

    def cmd_cmd(self, word, framing):
        self.logger.protocol("SDM < %#010x %s", word, framing.name)
        return self.port.SDM_CMD.cmd((word & 0xFFFFFFFF) | (int(framing) << 32),
                                     read_tdo = False)

    def rsp_cmd(self):
        return self.port.SDM_RSP.cmd(0, read_tdo = True,
                                     return_type = self.rsp_unpack)

    def rsp_unpack(self, tdo):
        raw_34 = int(tdo)
        w, h = (raw_34 >> 2) & 0xFFFFFFFF, RspFraming(raw_34 & 0x3)
        self.logger.protocol("SDM > %#010x %s", w, h.name)
        return w, h

    def cmd(self, word, framing):
        self.port.execute([self.cmd_cmd(word, framing)])

    def rsp(self):
        rx = self.rsp_cmd()
        self.port.execute([rx])
        return rx.tdo

    # ------------------------------------------------------------------
    # SDM frame I/O
    # ------------------------------------------------------------------

    def do_io(self, cmd):
        """Send a command frame and receive a response frame."""
        self._send_frame(cmd)
        return self._recv_frame()

    def nop(self):
        self.port.execute([self.cmd_cmd(0, CmdFraming.IDLE)])

    def _send_frame(self, words):
        """Send a list of 32-bit words as one CMD frame.

        Posts all shifts in batches, only awaiting the last one
        per batch to let the JTAG adapter aggregate.
        """
        tap = self.port

        todo = []
        todo.append(self.cmd_cmd(0, CmdFraming.IDLE))

        # Send command words in batches
        n = len(words)
        framing = CmdFraming.MORE
        for batch_start in range(0, n, _BATCH_SIZE):
            batch_end = min(batch_start + _BATCH_SIZE, n)
            for i in range(batch_start, batch_end):
                if i == n - 1:
                    framing = CmdFraming.LAST
                todo.append(self.cmd_cmd(words[i], framing))
                todo.append(self.port.cmd_run(16))
            self.port.execute(todo)
            todo = []

    def _recv_frame(self, max_silent=10):
        """Receive one response frame from RSP channel.

        Posts batched zero-shifts, reads TDO, collects words
        until LAST framing or timeout.
        """
        tap = self.port
        words = []
        rsp_count = None
        silent_to_go = max_silent
        interval = 0.001

        while True:
            # Determine how many words to read in this batch
            if rsp_count is not None:
                remaining = rsp_count - len(words)
            else:
                remaining = 1  # start with single reads until we know count
            to_rx = min(max(remaining, 1), _BATCH_SIZE)

            # Post batch of RSP shifts
            todo = []
            transfers = []
            for _ in range(to_rx):
                rx = self.rsp_cmd()
                transfers.append(rx)
                todo.append(rx)
                todo.append(self.port.cmd_run(16))

            self.port.execute(todo)

            had_rx = False

            # Process results
            for op in transfers:
                word, framing = op.tdo

                if framing in [RspFraming.IDLE, RspFraming.INVAL]:
                    continue

                had_rx = True
                words.append(word)

                if rsp_count is None:
                    rsp_count = 1 + ((word >> 12) & 0x7FF)

                if framing == RspFraming.LAST or len(words) >= rsp_count:
                    return words

            if had_rx:
                silent_to_go = max_silent
                interval = 0.001
            elif silent_to_go <= 0:
                raise TimeoutError("No response from SDM")
            else:
                silent_to_go -= 1
                time.sleep(interval)
                interval *= 2

        return words

    def _resync(self, nonce = None, max_retries=1):
        self.logger.protocol("SDM Wakeup")
        self.port.SDM_WAKEUP.shift(BitString(1, 1))
        for _ in range(20):
            self.port.run(512)
            time.sleep(512e-6)

        for retry in range(max_retries-1, -1, -1):
            self.logger.protocol("SDM Flush, retry %d", retry)
            self.cmd(0, CmdFraming.IDLE)
            self.cmd(0, CmdFraming.INVAL)
            self.cmd(0, CmdFraming.LAST)

            ok = False
            for retry in range(32, -1, -1):
                word, framing = self.rsp()
                if framing == RspFraming.LAST:
                    ok = True
                    break
            if not ok:
                if not retry:
                    raise TimeoutError("Unable to sync")
                continue

        if nonce is None:
            nonce = random.randint(0, 1<<32)
        self.logger.protocol("SDM Flush, Send nonce")
        self._send_frame([0xf0001001, nonce])

        # Drain stale RSP data
        for retry in range(32, -1, -1):
            if not retry:
                raise TimeoutError("Unable to sync")

            word, framing = self.rsp()
            if word & 0xfffff000 != 0xf0001000 or framing != RspFraming.MORE:
                continue
            word, framing = self.rsp()
            if word == nonce and framing == RspFraming.LAST:
                return

    def sync(self, nonce=None):
        """SDM sync with flush phase before the SYNC command."""

        self._resync(nonce = nonce)
        self.port.run(32)
