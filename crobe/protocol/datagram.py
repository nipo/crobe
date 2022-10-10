from . import base, pipe
from ..db import Db

__all__ = ["Interface", "Receive", "Send"]

class DatagramPipe(pipe.Interface):
    def __init__(self, port):
        super().__init__(port, "pipe")

    def execute(self, operation_list, timeout = None):
        pending = []
        rm = {}
        for op in operation_list:
            if isinstance(op, pipe.Write):
                pending.append(self.port.cmd_send(op.data))
            elif isinstance(op, pipe.Read):
                r = self.port.cmd_receive()
                rm[op] = r
                pending.append(r)
            elif isinstance(op, base.Reset):
                pending.append(op)
            else:
                self.logger.warning("Ignored unknown op %s", op)
        self.port.execute(pending, timeout = timeout)

        for op, r in rm.items():
            op.data = r.data

class Interface(base.Interface):
    """
    Bidir datagram interface
    """
    db = Db("Protocol handler")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-datagram")

    def freq_update(self, freq):
        return None
        
    def receive(self, context = None, timeout = None):
        """
        See cmd_receive()
        """
        op = self.cmd_receive(context = context)
        self.execute([op], timeout)
        return op.data

    def send(self, data, context = None, timeout = None):
        """
        See cmd_send()
        """
        op = self.cmd_send(data, context = context)
        self.execute([op], timeout)

    def send_receive(self, data, timeout = None, context = None):
        """
        See cmd_send(), cmd_receive()
        """
        s = self.cmd_send(data, context = context)
        r = self.cmd_receive(context = context)
        self.execute([s, r], timeout = timeout)
        return r.data

    def cmd_receive(self, context = None):
        """
        Returns a receive operation.

        :param context: Addressing context
        """
        return Receive(context = context)

    def cmd_send(self, data, context = None):
        """
        Returns a send operation for `data`

        :param context: Addressing context
        """
        return Send(data)

    def child_spawn(self, sub):
        return self.db.call(sub, self)

    def _execute(self, operation_list, timeout = None):
        ...

    def as_pipe(self):
        return DatagramPipe(self)
        
class Operation(object):
    def __repr__(self):
        return str(self)

class Send(Operation):
    def __init__(self, data, context = None):
        self.data = data
        self.context = context
        
    def __str__(self):
        return "<%s %s %s>" % (self.__class__.__name__, self.data, self.context)

class Receive(Operation):
    def __init__(self, context = None):
        self.context = context
        self.rcontext = None
        self.data = None

    def receive_done(self, data, context = None):
        self.data = data
        self.rcontext = context
        
    def __str__(self):
        return "<%s %s>" % (self.__class__.__name__, self.context)
