from . import base
from collections import deque
from ..model import PortComponent
from ..db import Db
import threading
import weakref
import time

__all__ = ["Interface", "Read", "Write", "BackgroundInterface"]

class Interface(base.Interface):
    """
    Bidir data pipe interface.
    """
    db = Db("Protocol handler")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-pipe")

    def freq_update(self, freq):
        return None
        
    def read(self, size, timeout = None):
        """
        See cmd_read()
        """
        op = self.cmd_read(size)
        self.execute([op], timeout)
        return op.data

    def write(self, data, timeout = None):
        """
        See cmd_write()
        """
        op = self.cmd_write(data)
        self.execute([op], timeout)

    def write_read(self, data, size, timeout = None):
        """
        See cmd_write_read()
        """
        w = self.cmd_write(data)
        r = self.cmd_read(size)
        self.execute([w, r], timeout)
        return r.data

    def cmd_read(self, size):
        """
        Returns reading of `size` bytes.

        :param int size: Size of transfer
        """
        return Read(size)

    def cmd_write(self, data):
        """
        Writes `data`
        """
        return Write(data)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

    def _execute(self, operation_list, timeout = None):
        ...

        
class Operation(object):
    def __repr__(self):
        return str(self)

class Write(Operation):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return "<Write %s>" % (self.data)

class Read(Operation):
    def __init__(self, size):
        self.size = size
        self.data = None

    def __str__(self):
        return "<Read %s>" % (self.size)
    
class BackgroundWriter(threading.Thread):
    def __init__(self, device):
        threading.Thread.__init__(self, daemon = True)
        self.device = device

        self.queue = deque()
        self.cond = threading.Condition()
        self.running = False
        self.exception = None

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False
        with self.cond:
            self.cond.notify_all()
        super().join()
        if self.exception:
            raise self.exception
        
    def write(self, data, timeout = None):
        with self.cond:
            self.queue.append((data, timeout))
            self.cond.notify_all()

    def flush(self):
        with self.cond:
            while self.queue and self.running:
                self.cond.wait()

    def run(self):
        with self.cond:
            while self.running:
                try:
                    data, timeout = self.queue.popleft()
                except IndexError:
                    self.cond.wait()
                    continue

                try:
                    self.device._write(data, timeout)
                except Exception as e:
                    self.exception = e
                    return
                self.cond.notify_all()

class BackgroundInterface(Interface):
    def __init__(self, port, name = None):
        super().__init__(port, name)
        self.__bw = BackgroundWriter(self)

    def start(self):
        super().start()
        self.logger.info("starting")
        self.__bw.start()

    def _execute(self, operation_list, timeout = None):
        for op in operation_list:
            if isinstance(op, Write):
                self.logger.info("to background writer: %s", op.data.hex())
                self.__bw.write(op.data, timeout)

            elif isinstance(op, Read):
                op.data = self._read(op.size, timeout)

            else:
                raise base.ProtocolError("Unknown Pipe operation %s" % type(op))
        self.__bw.flush()
#        time.sleep(.01)

    def _write(self, data, timeout = None):
        raise NotImplementedError()

    def _read(self, size, timeout = None):
        raise NotImplementedError()

class Closed(Exception):
    pass
    
class Responder(PortComponent):
    def __init__(self, pipe, name = "session"):
        super().__init__(pipe, name)
        self.buffer = b''

    def refill(self, count = None):
        if count is None:
            self.wait_more()
        else:
            while len(self.buffer) < count:
                self.wait_more()

    def wait_more(self):
        d = self.port.read(1)
        if not d:
            raise Closed()
        self.logger.protocol("> %s", d.hex())
        self.buffer += d
        
    def read(self, count):
        self.refill(count)
        blob = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return blob

    def write(self, data):
        while data:
            try:
                self.logger.protocol("< todo %s", data.hex())
                written = self.port.write(data)
            except Exception:
                raise Closed()
            if written:
                self.logger.protocol("< %s", data[:written].hex())
            data = data[written:]
