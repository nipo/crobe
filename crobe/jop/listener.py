"""TCP listener implementing the etherlink 5-socket handshake plus
the single-threaded synchronous session loop.

Single-client at a time: while one session holds the data sockets,
new incoming connections receive ``SERVER_BUSY\\0`` and close. After
the session ends (DISCONNECT or socket loss), a fresh client may
connect.

Handshake (matches Intel's reference verbatim so jtagd plugs in
unchanged):

1. Server accepts CTRL → sends NUL-terminated welcome banner with a
   server-chosen ``HANDLE`` integer.
2. Client replies ``"Control HANDLE=<int>\\0"``.
3. Server replies ``"READY\\0"``.
4. Server accepts each of MGMT, MGMT_RSP, H2T, T2H in order. For each:
   client sends ``"<sock_name> HANDLE=<int>\\0"``, server replies
   ``"READY\\0"``.
5. After all five, server sends a final ``"READY\\0"`` on CTRL.

Session loop: poll() over CTRL, H2T, MGMT plus the listening socket
(to reject 6th connections during the session). Each readable triggers
a ``recv`` into the per-socket buffer; the buffer is then drained for
complete frames or NUL-terminated lines. ``interface.execute(...)`` is
called inline in the loop thread — TCP backpressure keeps the peer in
step. T2H / MGMT_RSP / CTRL replies are written from the same thread,
so no locking is needed.
"""

import collections
import logging
import secrets
import selectors
import socket

from ..bitstring import BitString
from ..jtag.walker import JtagTmsWalker

from . import bytestream as bs
from . import control
from . import framing


_logger = logging.getLogger("jop.listener")


class _HandshakeError(Exception):
    pass


class JopListener:
    """Bind and serve. One :meth:`serve_forever` call accepts sessions
    sequentially, one client at a time.
    """

    def __init__(self, interface, *, host="::", port=1259,
                 mgmt_support=False, logger=None):
        self._interface = interface
        self._host = host
        self._port = port
        self._mgmt_support = mgmt_support
        self.logger = logger or _logger
        self._listen_sock = None

    def serve_forever(self):
        """Bind and run the accept/session loop until interrupted."""
        self._listen_sock = self._bind()
        self.logger.info("JoP listener on [%s]:%d for %s",
                         self._host, self._port, self._interface_name())
        try:
            while True:
                self._accept_one_session()
        finally:
            self._listen_sock.close()
            self._listen_sock = None

    def _bind(self):
        # Prefer IPv6 with v4-mapped fallback so a single bind serves both.
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            try:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except (AttributeError, OSError):
                pass
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self._host, self._port))
            s.listen(8)
            return s
        except OSError:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self._host, self._port))
            s.listen(8)
            return s

    def _interface_name(self):
        try:
            return self._interface.fqdn
        except AttributeError:
            return getattr(self._interface, "name", "<jtag>")

    def _accept_one_session(self):
        ctrl_sock, ctrl_buf = self._accept_with_buffer()
        peer = ctrl_sock.getpeername()
        self.logger.info("CTRL connection from %s", peer)
        sockets = {control.SOCK_CONTROL: (ctrl_sock, ctrl_buf)}
        try:
            self._handshake(ctrl_sock, ctrl_buf, sockets)
        except _HandshakeError as e:
            self.logger.warning("Handshake failed: %s", e)
            for s, _ in sockets.values():
                _shutdown_close(s)
            return

        session = _JopSession(
            interface=self._interface,
            listen_sock=self._listen_sock,
            ctrl=sockets[control.SOCK_CONTROL],
            mgmt=sockets[control.SOCK_MGMT],
            mgmt_rsp=sockets[control.SOCK_MGMT_RSP],
            h2t=sockets[control.SOCK_H2T],
            t2h=sockets[control.SOCK_T2H],
            mgmt_support=self._mgmt_support,
            logger=self.logger,
        )
        try:
            session.serve()
        finally:
            for s, _ in sockets.values():
                _shutdown_close(s)

    def _accept_with_buffer(self):
        sock, _addr = self._listen_sock.accept()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return sock, framing.FrameBuffer()

    def _handshake(self, ctrl_sock, ctrl_buf, sockets):
        handle = self._random_handle()
        welcome = control.welcome_message(
            mgmt_support=1 if self._mgmt_support else 0,
            h2t_rx_buff_sz=control.DEFAULT_H2T_BUFF_SZ,
            mgmt_rx_buff_sz=control.DEFAULT_MGMT_BUFF_SZ,
            ctrl_rx_buff_sz=control.DEFAULT_CTRL_BUFF_SZ,
            handle=handle,
        )
        ctrl_sock.sendall(welcome)
        self._expect_handle(ctrl_sock, ctrl_buf,
                            control.SOCK_CONTROL, handle)
        ctrl_sock.sendall(control.READY_MSG)

        order = [
            control.SOCK_MGMT,
            control.SOCK_MGMT_RSP,
            control.SOCK_H2T,
            control.SOCK_T2H,
        ]
        for name in order:
            sock, buf = self._accept_with_buffer()
            try:
                self._expect_handle(sock, buf, name, handle)
            except _HandshakeError:
                try:
                    sock.sendall(control.NOT_READY_MSG)
                except OSError:
                    pass
                _shutdown_close(sock)
                raise
            sock.sendall(control.READY_MSG)
            sockets[name] = (sock, buf)

        # Final READY on CTRL — "all five sockets bound, go".
        ctrl_sock.sendall(control.READY_MSG)

    def _expect_handle(self, sock, buf, sock_name, handle):
        expected = control.expected_handle_message(sock_name, handle)
        line = _recv_nul_into(sock, buf, max_len=4096)
        if line is None:
            raise _HandshakeError(f"EOF before {sock_name} ack")
        if line + b"\0" != expected:
            raise _HandshakeError(
                f"bad handle ack on {sock_name}: got {(line + b'\0')!r}, "
                f"expected {expected!r}")

    @staticmethod
    def _random_handle():
        # Non-zero per Intel's reference.
        v = 0
        while v == 0:
            v = secrets.randbits(31)
        return v


def _recv_nul_into(sock, buf, *, max_len):
    """Block on ``sock`` until ``buf`` yields a NUL-terminated message
    or EOF. Returns the message bytes (no NUL) or ``None`` on EOF."""
    while True:
        line = buf.take_until_nul()
        if line is not None:
            return line
        if len(buf.buf) > max_len:
            raise _HandshakeError(f"handshake message too long ({len(buf.buf)} bytes)")
        chunk = sock.recv(64)
        if not chunk:
            return None
        buf.feed(chunk)


def _shutdown_close(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class _JopSession:
    """Per-connection JoP session driver — single-threaded poll loop."""

    def __init__(self, *, interface, listen_sock,
                 ctrl, mgmt, mgmt_rsp, h2t, t2h,
                 mgmt_support, logger):
        self._interface = interface
        self._listen_sock = listen_sock
        self._ctrl_sock, self._ctrl_buf = ctrl
        self._mgmt_sock, self._mgmt_buf = mgmt
        self._mgmt_rsp_sock, _ = mgmt_rsp
        self._h2t_sock, self._h2t_buf = h2t
        self._t2h_sock, _ = t2h
        self._mgmt_support = mgmt_support
        self.logger = logger

        self._walker = JtagTmsWalker(interface)
        self._decoder = bs.JopDecoder()
        self._encoder = bs.JopEncoder()
        # Pending TDO-capture descriptors (FIFO depth 2 on-chip).
        self._capture_fifo = collections.deque()
        # Bits remaining in the head capture window.
        self._head_remaining = 0

        # Loopback knobs. SERVER_LOOPBACK is the etherlink-level switch
        # (Intel's reference echoes H2T headers + payload back as T2H);
        # #HW_LOOPBACK is the driver-level switch that on real hardware
        # would enable the streaming-debug-IP's internal loopback CSR.
        # We don't have an IP — we collapse both into a single "echo
        # H2T to T2H without decoding" mode, which is enough to let
        # Intel's remote_debug_tester_app exercise our wire layer.
        self._server_loopback = False
        self._hw_loopback = False
        # Driver-param store. Currently only #HW_LOOPBACK is recognised;
        # other names are accepted into the dict but not interpreted.
        self._driver_params = {"#HW_LOOPBACK": "0"}

        self._done = False

    @property
    def _loopback_active(self):
        return self._server_loopback or self._hw_loopback

    def serve(self):
        sel = selectors.DefaultSelector()
        sel.register(self._ctrl_sock, selectors.EVENT_READ, "ctrl")
        sel.register(self._h2t_sock, selectors.EVENT_READ, "h2t")
        sel.register(self._mgmt_sock, selectors.EVENT_READ, "mgmt")
        sel.register(self._listen_sock, selectors.EVENT_READ, "listen")
        try:
            while not self._done:
                events = sel.select()
                for key, _mask in events:
                    if self._done:
                        break
                    tag = key.data
                    if tag == "listen":
                        self._reject_extra()
                    elif tag == "ctrl":
                        if not self._on_ctrl_readable():
                            self._done = True
                    elif tag == "h2t":
                        if not self._on_h2t_readable():
                            self._done = True
                    elif tag == "mgmt":
                        if not self._on_mgmt_readable():
                            self._done = True
        finally:
            sel.close()

    # --- accept-during-session ---

    def _reject_extra(self):
        try:
            sock, _ = self._listen_sock.accept()
        except OSError:
            return
        peer = ()
        try:
            peer = sock.getpeername()
        except OSError:
            pass
        self.logger.info("Rejecting %s — session active", peer)
        try:
            sock.sendall(control.REJECT_MSG)
        except OSError:
            pass
        _shutdown_close(sock)

    # --- CTRL ---

    def _on_ctrl_readable(self):
        chunk = _recv_chunk(self._ctrl_sock)
        if chunk is None:
            return False
        self._ctrl_buf.feed(chunk)
        while True:
            line = self._ctrl_buf.take_until_nul()
            if line is None:
                return True
            keep_open = self._handle_ctrl_line(line.decode("ascii", "replace"))
            if not keep_open:
                return False

    def _handle_ctrl_line(self, line):
        verb, args = control.parse_control_command(line)
        self.logger.debug("CTRL <- %s %s", verb, args)
        sock = self._ctrl_sock
        if verb == control.CMD_PING:
            sock.sendall(control.RSP_PING)
            return True
        if verb == control.CMD_GET_PARAM:
            name = args[0] if args else ""
            value = self._get_param(name) if name else None
            if value is None:
                self.logger.warning("GET_PARAM %r — unknown parameter, "
                                    "replying with GET_PARAM_FAILURE", name)
                sock.sendall(control.RSP_GET_PARAM_FAIL)
            else:
                sock.sendall(value.encode("ascii") + b"\0")
            return True
        if verb == control.CMD_SET_PARAM:
            if len(args) >= 2 and self._set_param(args[0], args[1]):
                self.logger.info("SET_PARAM %s=%r — accepted", args[0], args[1])
                sock.sendall(control.RSP_SET_PARAM_ACK)
            else:
                self.logger.warning("SET_PARAM %r — unknown parameter or bad "
                                    "syntax, replying with SET_PARAM_FAIL_ACK",
                                    args)
                sock.sendall(control.RSP_SET_PARAM_FAIL)
            return True
        if verb == control.CMD_GET_DRIVER_PARAM:
            name = args[0] if args else ""
            value = self._get_driver_param(name) if name else None
            if value is None:
                self.logger.warning("GET_DRIVER_PARAM %r — unknown, "
                                    "replying with GET_PARAM_FAILURE", name)
                sock.sendall(control.RSP_GET_PARAM_FAIL)
            else:
                sock.sendall(value.encode("ascii") + b"\0")
            return True
        if verb == control.CMD_SET_DRIVER_PARAM:
            if len(args) >= 2 and self._set_driver_param(args[0], args[1]):
                sock.sendall(control.RSP_SET_PARAM_ACK)
            else:
                self.logger.warning("SET_DRIVER_PARAM %r — unknown driver "
                                    "parameter, replying with "
                                    "SET_PARAM_FAIL_ACK", args)
                sock.sendall(control.RSP_SET_PARAM_FAIL)
            return True
        if verb == control.CMD_DISCONNECT:
            self.logger.info("DISCONNECT requested by client")
            sock.sendall(control.RSP_DISCONNECT)
            return False
        self.logger.warning("CTRL: unrecognised command %r (full line %r)",
                            verb, line)
        sock.sendall(control.RSP_UNRECOGNIZED)
        return True

    def _get_param(self, name):
        if name == control.PARAM_MGMT_SUPPORT:
            return "1" if self._mgmt_support else "0"
        if name == control.PARAM_H2T_RX_BUFF_SZ:
            return str(control.DEFAULT_H2T_BUFF_SZ)
        if name == control.PARAM_MGMT_RX_BUFF_SZ:
            return str(control.DEFAULT_MGMT_BUFF_SZ)
        if name == control.PARAM_CTRL_RX_BUFF_SZ:
            return str(control.DEFAULT_CTRL_BUFF_SZ)
        if name == control.PARAM_T2H_NAGLE:
            return "0"
        if name == control.PARAM_MGMT_RSP_NAGLE:
            return "0"
        if name == control.PARAM_SERVER_LOOPBACK:
            return "0"
        return None

    def _set_param(self, name, value):
        if name == control.PARAM_SERVER_LOOPBACK:
            self._server_loopback = (value.strip() == "1")
            self.logger.info("SERVER_LOOPBACK %s",
                             "enabled" if self._server_loopback else "disabled")
            return True
        # Other known parameters are advertised statically; accept the
        # write but don't actually mutate state (Nagle, buffer sizes).
        return self._get_param(name) is not None

    def _get_driver_param(self, name):
        return self._driver_params.get(name)

    def _set_driver_param(self, name, value):
        if name == "#HW_LOOPBACK":
            self._hw_loopback = (value.strip() == "1")
            self._driver_params[name] = value
            self.logger.info("#HW_LOOPBACK %s",
                             "enabled" if self._hw_loopback else "disabled")
            return True
        return False

    # --- MGMT drain ---

    def _on_mgmt_readable(self):
        chunk = _recv_chunk(self._mgmt_sock)
        if chunk is None:
            return False
        self._mgmt_buf.feed(chunk)
        try:
            while True:
                pkt = self._mgmt_buf.take_mgmt_packet()
                if pkt is None:
                    return True
                self.logger.warning(
                    "MGMT packet received unexpectedly: %d bytes "
                    "(channel=%d sop=%d eop=%d): %s — server advertised "
                    "MGMT_SUPPORT=0 and has no MGMT decoder; payload "
                    "ignored, no MGMT_RSP will be generated.",
                    len(pkt.payload), pkt.channel, pkt.sop, pkt.eop,
                    pkt.payload.hex())
        except framing.GuardbandError as e:
            self.logger.warning("MGMT framing error: %s", e)
            return False

    # --- H2T data plane ---

    def _on_h2t_readable(self):
        chunk = _recv_chunk(self._h2t_sock)
        if chunk is None:
            return False
        self._h2t_buf.feed(chunk)
        try:
            while True:
                pkt = self._h2t_buf.take_h2t_packet()
                if pkt is None:
                    return True
                self._handle_h2t_packet(pkt)
        except framing.GuardbandError as e:
            self.logger.warning("H2T framing error: %s", e)
            return False

    def _handle_h2t_packet(self, pkt):
        self.logger.debug("H2T %d bytes (channel=%d sop=%d eop=%d): %s",
                          len(pkt.payload), pkt.channel,
                          pkt.sop, pkt.eop, pkt.payload.hex())
        if self._loopback_active:
            self._echo_to_t2h(pkt)
            return
        try:
            ops = self._decoder.feed(pkt.payload)
        except ValueError as e:
            self.logger.warning(
                "H2T decoder error: %s — payload=%s, dropping packet "
                "and resetting decoder state.", e, pkt.payload.hex())
            self._decoder = bs.JopDecoder()
            return
        for op in ops:
            self._dispatch_op(op, pkt.channel, pkt.conn_id)

    def _echo_to_t2h(self, pkt):
        """Loopback path: re-emit the H2T packet on T2H verbatim."""
        self.logger.debug("T2H (loopback) %d bytes (channel=%d sop=%d eop=%d)",
                          len(pkt.payload), pkt.channel, pkt.sop, pkt.eop)
        out = framing.H2tPacket(
            sop=pkt.sop, eop=pkt.eop, conn_id=pkt.conn_id,
            channel=pkt.channel, payload=pkt.payload)
        self._t2h_sock.sendall(out.encode())

    def _dispatch_op(self, op, channel, conn_id):
        if isinstance(op, bs.RetrieveInfo):
            self._send_t2h(bytes([bs.CONFIG_INFO_RESPONSE_BYTE]),
                           channel, conn_id, eop=True)
        elif isinstance(op, bs.ResetTdoFifo):
            self._capture_fifo.clear()
            self._head_remaining = 0
        elif isinstance(op, bs.PushTdoCapture):
            if len(self._capture_fifo) >= bs.TDO_FIFO_DEPTH:
                self.logger.warning(
                    "TDO-enable FIFO overflow — dropping oldest entry")
                self._capture_fifo.popleft()
            self._capture_fifo.append(op)
            if self._head_remaining == 0 and self._capture_fifo:
                self._head_remaining = self._capture_fifo[0].duration
        elif isinstance(op, bs.Shift):
            self._do_shift(op, channel, conn_id)

    def _do_shift(self, op, channel, conn_id):
        tdo = self._walker.process(op.tms, op.tdi)
        # Accumulated bytes from completed/partial capture windows for
        # this shift, plus a flag tracking whether any completed window
        # asked for EOP.
        out = bytearray()
        any_eop = False
        captured_bits = BitString()

        for i in range(len(tdo)):
            if self._head_remaining == 0:
                continue
            head = self._capture_fifo[0]
            if head.tdo_enable:
                captured_bits += BitString(int(tdo[i]), 1)
            self._head_remaining -= 1
            if self._head_remaining == 0:
                if len(captured_bits) and head.tdo_enable:
                    chunk, _marks = self._encoder.emit_window(
                        captured_bits, eop=head.eop_gen)
                    out.extend(chunk)
                    captured_bits = BitString()
                if head.eop_gen:
                    any_eop = True
                self._capture_fifo.popleft()
                if self._capture_fifo:
                    self._head_remaining = self._capture_fifo[0].duration

        # Bits captured for a still-open window are held in the encoder.
        if len(captured_bits):
            chunk, _ = self._encoder.emit_window(captured_bits, eop=False)
            out.extend(chunk)

        if out:
            self._send_t2h(bytes(out), channel, conn_id, eop=any_eop)

    def _send_t2h(self, payload, channel, conn_id, *, eop):
        self.logger.debug("T2H %d bytes (channel=%d sop=1 eop=%d): %s",
                          len(payload), channel, int(eop), payload.hex())
        pkt = framing.H2tPacket(
            sop=True, eop=eop, conn_id=conn_id,
            channel=channel, payload=payload)
        self._t2h_sock.sendall(pkt.encode())


def _recv_chunk(sock, size=4096):
    """Blocking ``recv`` returning bytes, or ``None`` on EOF."""
    try:
        chunk = sock.recv(size)
    except (ConnectionResetError, OSError):
        return None
    if not chunk:
        return None
    return chunk
