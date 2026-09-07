import time
from math import gcd
from ....model import PortComponent
from ....protocol import datagram, spi
from collections import deque


class SpiFifoTransport(PortComponent):
    """
    Host side of ``nsl_spi.fifo_transport.spi_fifo_transport_slave``.

    The FPGA slave embeds a bidirectional FIFO inside a plain SPI bus.
    For an ``N`` wide FIFO, every SPI word is ``N + 2`` bits, sent MSB
    first::

        [READY] [VALID] [N data bits, MSB first]

    ``READY`` tells the peer we can accept a word, ``VALID`` tells the
    peer our data bits are meaningful.  After each word both parties
    decide, from the bits just exchanged, whether their outgoing word was
    accepted and whether the incoming word must be kept.  The slave
    accepts pipelining, i.e. several words shifted back to back inside a
    single CS assertion.

    This is the SPI counterpart of
    :class:`crobe.component.nsl.bnoc.jtag_fifo_transport.JtagFifoTransport`;
    the JTAG DR shift is replaced by an SPI transaction where MOSI
    carries our ``[READY][VALID][data]`` word and MISO carries the
    slave's.

    :param port: an :class:`crobe.protocol.spi.Target` (anything exposing
        ``cmd_cs`` / ``cmd_shift`` / ``execute``).
    :param width: FIFO width in bits, must match the slave ``width_c``.

    SPI adapters only shift whole bytes, so words are grouped into the
    smallest run that lands on a byte boundary (8 words for the 9-bit
    framed FIFO, 1 word when ``width + 2`` is already a multiple of 8).

    Flow control: the slave decides per word whether it accepts our
    outgoing data (``READY`` in the word it returns), and it may reject a
    word yet accept a later one in the same CS burst once its downstream
    FIFO drains.  An outgoing word cannot be un-sent, so we can only ever
    put ``VALID`` on **one** word per SPI transaction (like the reference
    ``spi_fifo_transport_master``); the remaining words of the burst are
    ``READY``-only and just drain the receive direction, which has no such
    hazard.
    """

    #: READY-only poll words per SPI transaction while draining the
    #: receive direction in bulk.
    BATCH = 64

    def __init__(self, port, width):
        PortComponent.__init__(self, port, "fifo_transport")

        self.width = width
        self.word_bits = width + 2
        self.READY = 1 << (width + 1)
        self.VALID = 1 << width
        self.DMASK = self.VALID - 1

        self.group_words = 8 // gcd(self.word_bits, 8)
        # Words per SPI transaction: a whole number of byte-aligned groups.
        self.round_words = max(
            self.group_words,
            (self.BATCH // self.group_words) * self.group_words,
        )

        self.tx_buf = deque()
        self.rx_buf = deque()
        self.total_rx = 0

    def extract(self, word):
        return bool(word & self.READY), bool(word & self.VALID), word & self.DMASK

    def _pack(self, words):
        mask = (1 << self.word_bits) - 1
        acc = 0
        for w in words:
            acc = (acc << self.word_bits) | (w & mask)
        return acc.to_bytes(len(words) * self.word_bits // 8, "big")

    def _unpack(self, blob, count):
        acc = int.from_bytes(blob, "big")
        mask = (1 << self.word_bits) - 1
        return [
            (acc >> ((count - 1 - i) * self.word_bits)) & mask
            for i in range(count)
        ]

    def write(self, data):
        for word in data:
            self.tx_buf.append(word)

    #: Consecutive idle SPI transactions that end a :meth:`read`.
    RX_IDLE_ROUNDS = 3
    #: Consecutive transactions with no TX progress before :meth:`flush`
    #: gives up on a wedged slave.
    TX_STALL_LIMIT = 100

    #: Put VALID on more than one word per SPI transaction.  The slave
    #: (``spi_fifo_transport_slave``) has a one-word rx buffer, so a second
    #: VALID word in the same burst is only taken if the framed consumer
    #: downstream drained the first between the two word slots.  We can tell
    #: from the returned READY bits exactly which words were taken -- but if
    #: the taken set is not a prefix (consumer stalled for ~1 word then
    #: recovered) the slave has swallowed a word out of order.  Safe only
    #: when the downstream framed FIFO never backpressures within a burst
    #: (deep enough for the largest frame).  On a non-prefix result this
    #: falls back to one-VALID-per-round for the rest of the session.
    TX_PIPELINE = True
    _tx_pipeline_ok = True

    def read(self):
        self.flush()
        idle = 0
        while idle < self.RX_IDLE_ROUNDS:
            n = len(self.rx_buf)
            self._io_round()
            idle = 0 if len(self.rx_buf) > n else idle + 1
        r = self.rx_buf
        self.rx_buf = deque()
        return list(r)

    def flush(self):
        """Shift out everything queued by :meth:`write`; rx words are kept
        in ``rx_buf`` for the next :meth:`read`."""
        stall = 0
        while self.tx_buf:
            before = len(self.tx_buf)
            self._io_round()
            if len(self.tx_buf) < before:
                stall = 0
            else:
                stall += 1
                if stall >= self.TX_STALL_LIMIT:
                    raise TimeoutError(
                        "fifo_transport: slave stopped accepting data, "
                        f"{len(self.tx_buf)} word(s) left to send")
                time.sleep(0.002)

    def _io_round(self):
        # How many leading tx words to offer this round.  One is always safe
        # (the reference master's behaviour); more only when TX_PIPELINE is on
        # and hasn't tripped its safety fallback.
        n_tx = 0
        if self.tx_buf:
            n_tx = 1
            if self.TX_PIPELINE and self._tx_pipeline_ok:
                n_tx = min(len(self.tx_buf), self.round_words)

        out_words = []
        for i in range(self.round_words):
            if i < n_tx:
                out_words.append(self.READY | self.VALID | (self.tx_buf[i] & self.DMASK))
            else:
                out_words.append(self.READY)

        shift = self.port.cmd_shift(self._pack(out_words), read_miso=True)
        self.port.execute([self.port.cmd_cs(True), shift, self.port.cmd_cs(False)])
        in_words = self._unpack(shift.miso, self.round_words)

        ok = False
        taken = 0          # leading run of accepted tx words
        gap = False        # an accepted word after a rejected one
        for i, (out_word, in_word) in enumerate(zip(out_words, in_words)):
            peer_ready, peer_valid, d = self.extract(in_word)

            if i < n_tx and (out_word & self.VALID):
                if peer_ready:
                    if taken == i:
                        taken += 1
                    else:
                        gap = True
                # else: rejected -- not counted

            if peer_valid:
                self.logger.protocol("> 0x%02x", d)
                self.rx_buf.append(d)
                self.total_rx += 1
                ok = True

        if gap:
            # the slave swallowed a word out of order -- disable pipelining and
            # let the caller's frame-level retry/timeout deal with the mess
            self._tx_pipeline_ok = False
            self.logger.warning(
                "fifo_transport: downstream backpressured mid-burst; "
                "TX pipelining disabled")

        for _ in range(taken):
            w = self.tx_buf.popleft()
            self.logger.protocol("< 0x%02x", w & self.DMASK)
            ok = True

        return ok


class SpiFramedGateway(PortComponent):
    """
    Frame-level (8 data bits + ``last``) gateway over
    ``nsl_spi.fifo_transport.spi_framed_transport_slave``.

    SPI counterpart of
    :class:`crobe.component.nsl.bnoc.jtag_framed_gateway.JtagFramedGateway`:
    a light-weight alternative to :class:`SpiFramedTransport` that exposes
    a plain ``frame_send`` / ``frame_recv`` / ``execute(cmd, rsp_size)``
    API instead of the :class:`crobe.protocol.datagram.Interface`
    protocol.  Where the JTAG gateway shifts dedicated send/receive user
    registers, SPI has a single full-duplex word so the ``READY`` /
    ``VALID`` handshake is delegated to :class:`SpiFifoTransport`.

    :param port: an :class:`crobe.protocol.spi.Target`.
    :param width: FIFO width, 9 for ``spi_framed_transport_slave``.
    """

    LAST = 1 << 8

    def __init__(self, port, width=9):
        PortComponent.__init__(self, port, "framed_gw")
        self.transport = SpiFifoTransport(port, width)
        self.left = []

    def execute(self, cmd, rsp_size=None):
        self.frame_send(cmd)
        if rsp_size == 0:
            self.transport.flush()
            return b''
        return self.frame_recv()

    def frame_send(self, frame):
        assert frame
        self.logger.protocol("< %s", bytes(frame).hex())
        enc = list(frame)
        enc[-1] |= self.LAST
        self.transport.write(enc)

    def frame_recv(self):
        retries = 3
        while True:
            for i, word in enumerate(self.left):
                if word & self.LAST:
                    frame = bytes([x & 0xff for x in self.left[:i + 1]])
                    self.left = self.left[i + 1:]
                    self.logger.protocol("> %s", frame.hex())
                    return frame

            more_data = self.transport.read()
            self.left += more_data

            if more_data:
                retries = 3
                continue

            time.sleep(0.05)
            retries -= 1
            if retries <= 0:
                return None


@spi.Target.db.register("framed_transport")
class SpiFramedTransport(datagram.Interface):
    """
    Framed (8 data bits + ``last``) datagram interface over
    ``nsl_spi.fifo_transport.spi_framed_transport_slave``.

    That slave fixes the FIFO width at 9 bits: bit 8 is the frame ``LAST``
    marker, bits 7:0 are the payload byte.  SPI counterpart of
    :class:`crobe.component.nsl.bnoc.jtag_fifo_transport.JtagFramedTransport`.

    Registered as the ``framed_transport`` SPI chip type, so it can be
    summoned from a root path, e.g.::

        .../kumi_mgmt_rp2(spi=0;1;2;3)/spi/cs0/framed_transport/kumi_mgmt_hdl/i2c/eeprom(saddr=0x50)
    """

    LAST = 1 << 8

    def __init__(self, port, width=9, name=None):
        super().__init__(port, f"{name or port.name}-framed")
        self.transporter = SpiFifoTransport(port, width)
        self.rx_buf = []

    #: Idle polls (each ~5 ms) tolerated before a pending receive is
    #: declared timed out.
    RECV_RETRIES = 200

    def _pop_frames(self, recv_pending):
        """Hand every complete frame in ``rx_buf`` to a pending receive.
        Returns True once all pending receives are satisfied."""
        while recv_pending:
            cut = next((i for i, w in enumerate(self.rx_buf) if w & self.LAST), None)
            if cut is None:
                return False
            frame = bytes([x & 0xff for x in self.rx_buf[:cut + 1]])
            self.rx_buf = self.rx_buf[cut + 1:]
            recv_pending.pop(0).receive_done(frame)
        return True

    def execute(self, operation_list, timeout=None):
        t = self.transporter
        recv_pending = []
        for op in operation_list:
            if isinstance(op, datagram.Send):
                enc = list(op.data)
                enc[-1] |= self.LAST
                t.write(enc)
            elif isinstance(op, datagram.Receive):
                recv_pending.append(op)
            else:
                self.logger.warning("Ignoring operation %s", op)

        if not recv_pending:
            t.flush()
            return

        # push every queued frame out; rx words seen along the way stay in
        # t.rx_buf
        t.flush()

        # Then poll one round at a time and stop the instant every pending
        # receive has its LAST-marked frame -- no gratuitous idle rounds
        # (each round is a full USB round trip to the transactor).
        idle = 0
        while True:
            while t.rx_buf:
                self.rx_buf.append(t.rx_buf.popleft())
            if self._pop_frames(recv_pending):
                return

            if t._io_round():
                idle = 0
            else:
                idle += 1
                if idle >= self.RECV_RETRIES:
                    raise TimeoutError(
                        f"framed_transport: {len(recv_pending)} receive(s) still "
                        f"pending, {len(self.rx_buf)} buffered words")
                time.sleep(0.005)
