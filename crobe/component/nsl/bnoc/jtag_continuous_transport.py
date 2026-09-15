import time
from ....bitstring import BitString
from ....model import PortComponent
from ....protocol import datagram
from collections import deque

class JtagContinuousTransport(PortComponent):
    def __init__(self, port, data_ir):
        PortComponent.__init__(self, port, "ct")

    def write(self, data):
        cmds = []
        for word in data:
            self.tx_buf.append(word)

    def read(self):
        ok = True
        while ok:
            if self.status_ir is not None:
                ok = self.do_io_speculative()
            else:
                ok = self.do_io_single()
        r = self.rx_buf
        self.rx_buf = deque()
        return list(r)
            
    def do_io_single(self):
        ok = False

        dout = (self.READY | self.VALID | self.tx_buf[0]) if self.tx_buf else 0
        din = self.port.dr_shift(self.data_ir, dout, self.width + 2, read_tdo = True)
        ready, valid, d = self.extract(din)

        if ready and self.tx_buf:
            self.logger.protocol("< 0x%02x", self.rx_buf[0])
            self.tx_buf.popleft()
            ok = True

        if valid:
            self.logger.protocol("> 0x%02x", d)
            self.rx_buf.append(d)
            self.total_rx += 1
            ok = True

        return ok

    def do_io_speculative(self):
        commands = []
        word_out = 0
        out_free = 64
        in_ready = 0
        ok = False

        status = self.port.cmd_dr_shift(self.status_ir, None, 32, read_tdo = True)
#        check = self.port.cmd_dr_shift(self.data_ir, 0, self.width + 2, read_tdo = True)
#        self.port.execute([status, check])
        self.port.execute([status])
        status = int(status.tdo)
#        ready, valid, d = self.extract(check.tdo)
        out_free = (status >> 16) & 0xffff
        in_ready = status & 0xffff

        self.logger.debug("Out free: %d, in ready: %d, to send: %d", out_free, in_ready, len(self.tx_buf))

#        if not ready and out_free:
#            self.logger.warning("Out free is non-zero, but not ready")
#            out_free = 0

        in_ready += 16
                
        while self.tx_buf and len(commands) < out_free:
            word = self.tx_buf.popleft()
            self.logger.protocol("< 0x%02x", word)
            commands.append(self.port.cmd_dr_shift(self.data_ir, self.VALID | self.READY | word, self.width + 2, read_tdo = True))
            ok = True
            word_out += 1

        while len(commands) < min(in_ready, 128):
            commands.append(self.port.cmd_dr_shift(self.data_ir, self.READY, self.width + 2, read_tdo = True))

        _commands = []
        for c in commands:
            _commands.append(c)
            _commands.append(self.port.cmd_run(10))
        self.port.execute(_commands)

        for i, c in enumerate(commands):
            sent_ready, sent_valid, sent_data = self.extract(int(c.tdi), False)
            recv_ready, recv_valid, recv_data = self.extract(int(c.tdo))

            if sent_valid > recv_ready:
                print(commands)
                print("Out free: %d, in ready: %d" % (out_free, in_ready))

                raise RuntimeError(f"Bad handshake at index {i}")

            if recv_valid:
                self.logger.protocol("> 0x%02x", recv_data)
                self.rx_buf.append(recv_data)
                self.total_rx += 1
                ok = True

        return ok

class JtagFramedTransport(datagram.Interface):
    def __init__(self, port, data_ir, status_ir = None, name = None):
        super().__init__(port, f"{name or port.name}-framed")
        self.transporter = JtagContinuousTransport(port, 9, data_ir, status_ir)
        self.rx_buf = []

    def execute(self, operation_list, timeout = None):
        recv_pending = []
        for op in operation_list:
            if isinstance(op, datagram.Send):
                enc = list(op.data)
                enc[-1] |= 0x100
                self.transporter.write(enc)
            elif isinstance(op, datagram.Receive):
                recv_pending.append(op)
            else:
                self.logger.warning("Ignoring operation %s", op)

        while recv_pending:
            more_data = self.transporter.read()

            self.rx_buf += more_data

            for i, word in enumerate(self.rx_buf):
                if word & 0x100:
                    frame = bytes([x & 0xff for x in self.rx_buf[:i+1]])
                    self.rx_buf = self.rx_buf[i+1:]
                    op = recv_pending.pop(0)
                    op.receive_done(frame)

                    if not recv_pending:
                        return

            if more_data:
                continue
            

        
