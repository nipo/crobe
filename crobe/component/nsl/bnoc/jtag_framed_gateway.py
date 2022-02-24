import time
from ....bitstring import BitString
from ....model import PortComponent

class JtagFramedGateway(PortComponent):
    def __init__(self, port, ir_send, ir_recv):
        PortComponent.__init__(self, port, "framed_gw")
        self.ir_send = ir_send
        self.ir_recv = ir_recv
        self.left = []
        
    def execute(self, cmd, rsp_size):
        self.send(cmd)
        return self.recv(rsp_size)

    def frame_send(self, frame):
        assert frame

        cmds = []
        for index, word in enumerate(frame):
            last = int(index == (len(frame) - 1))
            self.logger.protocol("< 0x%02x, %s", word, "last" if last else "-")
            cmds += [
                self.port.cmd_dr_shift(self.ir_send, (last << 8) | word, 9, read_tdo = False),
                ]
        self.port.execute(cmds)
            
    def frame_recv(self):
        for retry in range(30):
            if any(x for (x, y) in self.left):
                ret = []
                while True:
                    last, d = self.left.pop(0)
                    ret.append(d)
                    if last:
                        return bytes(ret)

            self.refill()
        raise RuntimeError("No data")

    def refill(self):
        rx = []
        for i in range(64):
            r = self.port.cmd_dr_shift(self.ir_recv, None, 10,
                                       read_tdo = True,
                                       return_type = int)
            rx.append(r)

        self.port.execute(rx)

        for poll in rx:
            valid = bool(poll.tdo & 0x200)
            last = bool(poll.tdo & 0x100)
            d = poll.tdo & 0xff

            self.logger.protocol("> 0x%02x, %s, %s", d, "last" if last else "-", "valid" if valid else "-")

            if valid:
                self.left.append((last, d))
