from ....model import PortComponent
import threading

class Router(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "mux")
        self.rx_queue_cond = threading.Condition(threading.Lock())
        self.waiting = {}
        self.reader = None
        
    def reset(self):
        self.waiting = {}
        
    def msg_send(self, dst, src, data):
        assert len(data) < (1 << 16) - 2
        route = dst | (src << 4)
        frame = bytes([route]) + data
        self.logger.debug("< %s", frame.hex())
        self.port.frame_send(frame)

    def msg_recv_all(self, dst, src):
        route = dst | (src << 4)

        while True:
            with self.rx_queue_cond:
                try:
                    return self.waiting.pop(route)
                except KeyError:
                    pass

                if self.reader:
                    self.rx_queue_cond.wait()
                    continue

                self.reader = self
                try:
                    frame = self.port.frame_recv()
                    self.logger.debug("> %s", frame.hex())
                    data = frame[1:]
                    if frame[0] in self.waiting:
                        self.waiting[frame[0]].append(data)
                    else:
                        self.waiting[frame[0]] = [data]
                finally:
                    self.reader = None
                    self.rx_queue_cond.notify_all()

class Route(PortComponent):
    def __init__(self, port, local_id, remote_id):
        PortComponent.__init__(self, port, "%d>%d" % (local_id, remote_id))
        self.local_id = local_id
        self.remote_id = remote_id
        self.waiting = []

    def flush(self):
        self.waiting = []
        
    def send(self, data):
        self.logger.debug("< %s", data.hex())
        self.port.msg_send(self.remote_id, self.local_id, data)

    def _wait(self):
        messages = self.port.msg_recv_all(self.local_id, self.remote_id)
        self.waiting += messages
    
    def _pop(self):
        while True:
            try:
                return self.waiting.pop()
            except:
                pass
            self._wait()

    def recv(self):
        r = self._pop()
        self.logger.debug("> %s", r.hex())
        return r
            
class FramedEndpoint(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "endpoint")
        self.last_tag = 0
        
    def execute(self, cmd, rsp_size):
        tag = (self.last_tag + 1) & 0xff
        self.last_tag = tag

        self.port.send(bytes([tag]) + bytes(cmd))
        rsp = self.port.recv()
        tag = rsp[0]
        data = rsp[1:]
        assert tag == self.last_tag
        if rsp_size is not None:
            if len(data) != rsp_size:
                self.logger.error("Received frame is %d bytes, expected %d", len(data), rsp_size)
                self.logger.error("> %s", data.hex())
                if len(data) < rsp_size:
                    raise ValueError("Short frame")
        return data

