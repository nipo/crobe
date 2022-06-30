from . import base
from collections import deque
from ..model import PortComponent
from ..db import Db
import threading
import weakref

__all__ = ["Interface", "Read", "Write", "WriteRead", "BackgroundInterface"]

class Interface(base.Interface):
    """
    Bidir data pipe interface.
    """
    db = Db("Protocol handler")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-pipe")
        
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
        op = self.cmd_write_read(data, size)
        self.execute([op], timeout)
        return op.rdata

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

    def cmd_write_read(self, wdata, rsize):
        """Writes `wdata` while reading rsize bytes.

        Both operations happen in the same time. This is mostly useful
        for pipelined processing where the whole write/read operation
        does not fit in the full IO buffers.

        """
        return WriteRead(wdata, rsize)

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
        return "<Read %d>" % (self.size)

class WriteRead(Operation):
    def __init__(self, wdata, rsize):
        self.wdata = wdata
        self.rsize = rsize
        self.rdata = None

    def __str__(self):
        return "<WriteRead %s %d>" % (self.wdata.hex(), self.rsize)



    
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
        while self.running:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                    if not self.running:
                        return
                    data, timeout = self.queue.popleft()
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
        self.__bw.start()

    def _execute(self, operation_list, timeout = None):
        for op in operation_list:
            if isinstance(op, Write):
                self.__bw.write(op.data, timeout)

            elif isinstance(op, Read):
                op.data = self._read(op.size, timeout)

            elif isinstance(op, WriteRead):
                self.__bw.write(op.wdata, timeout)
                op.rdata = self._read(op.rsize, timeout)

            else:
                raise base.ProtocolError("Unknown Pipe operation %s" % type(op))
        self.__bw.flush()

    def _write(self, data, timeout = None):
        raise NotImplementedError()

    def _read(self, size, timeout = None):
        raise NotImplementedError()
