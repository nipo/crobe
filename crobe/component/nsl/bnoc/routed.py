from ....model import PortComponent
import threading
import time

class Router(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "mux")
        self.rx_queue_cond = threading.Condition(threading.Lock())
        self.waiting = {}
        self.reader = None
        port.child_add(self)
        
    def reset(self):
        self.waiting = {}
        
    def msg_send(self, dst, src, data):
        assert len(data) < (1 << 16) - 2
        route = dst | (src << 4)
        frame = bytes([route]) + data
        self.logger.debug("< %s", frame.hex())
        self.port.frame_send(frame)

    def msg_recv_all(self, dst, src, timeout = None):
        deadline = None
        if timeout:
            deadline = time.time() + timeout
        
        route = dst | (src << 4)

        while True:
            if deadline is not None:
                if time.time() >= deadline:
                    return

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
                    if frame is None:
                        self.logger.debug("> / (%s, %s)", timeout ,deadline)
                        continue
                    self.logger.debug("> %s", frame.hex())
                    if not frame:
                        continue
                    data = frame[1:]
                    if frame[0] in self.waiting:
                        self.waiting[frame[0]].append(data)
                    else:
                        self.waiting[frame[0]] = [data]
                finally:
                    self.reader = None
                    self.rx_queue_cond.notify_all()

    def route(self, local_id, remote_id):
        return Route(self, local_id, remote_id)
                    
class Route(PortComponent):
    def __init__(self, port, local_id, remote_id):
        PortComponent.__init__(self, port, "%d>%d" % (local_id, remote_id))
        self.local_id = local_id
        self.remote_id = remote_id
        self.waiting = []
        port.child_add(self)

    def flush(self):
        self.waiting = []
        
    def send(self, data):
        self.logger.debug("< %s", data.hex())
        self.port.msg_send(self.remote_id, self.local_id, data)

    def _wait(self, timeout = None):
        messages = self.port.msg_recv_all(self.local_id, self.remote_id, timeout = timeout)
        self.logger.debug("wait > %s", messages)
        if messages:
            self.waiting += messages
    
    def _pop(self, timeout = None):
        deadline = None
        if timeout:
            deadline = time.time() + timeout
        while True:
            if deadline is not None:
                if time.time() >= deadline:
                    self.logger.debug("_pop timeout")
                    return
            try:
                return self.waiting.pop()
            except:
                self.logger.debug("_pop fail")
                pass
            self._wait(timeout = timeout)

    def recv(self, timeout = None):
        r = self._pop(timeout)
        if r:
            self.logger.debug("> %s", r.hex())
        return r
            
    def framed_endpoint(self):
        return FramedEndpoint(self)
                    
class FramedEndpoint(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "endpoint")
        self.last_tag = 0
        
    def frame_send(self, cmd):
        tag = (self.last_tag + 1) & 0xff
        self.last_tag = tag
        self.port.send(bytes([tag]) + bytes(cmd))
        return tag

    def frame_recv(self, size = None, tag = None, timeout = None):
        rsp = self.port.recv(timeout)
        if timeout is not None and rsp is None:
            return None
        rx_tag = rsp[0]
        data = rsp[1:]
        if tag is not None:
            assert rx_tag == tag
        if size is not None:
            if len(data) != size:
                self.logger.error("Received frame is %d bytes, expected %d", len(data), size)
                self.logger.error("> %s", data.hex())
                if len(data) < size:
                    raise ValueError("Short frame")
        return data
    
    def execute(self, cmd, rsp_size, timeout = None):
        tx_tag = self.frame_send(cmd)

        if rsp_size == 0:
            return

        return self.frame_recv(size = rsp_size,
                               tag = tx_tag,
                               timeout = timeout)
