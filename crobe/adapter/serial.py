from . import model
import serial
import serial.tools.list_ports
from ..protocol import pipe
import threading

__all__ = []

class SerialInterface(pipe.BackgroundInterface):
    PARITY_MAP = dict(
        N = serial.PARITY_NONE,
        E = serial.PARITY_EVEN,
        O = serial.PARITY_ODD,
        M = serial.PARITY_MARK,
        S = serial.PARITY_SPACE,
    )
    
    def __init__(self, adapter, dev):
        self.params = dict(
            dev = dev,
            rate = 115200,
            bits = 8,
            parity = "N",
            stop = 1,
            rtscts = False,
        )
        self.io = None
        pipe.Interface.__init__(self, adapter, adapter.name)

    def freq_update(self, freq):
        return self.params["rate"]

    def option_set(self, opt):
        try:
            k, v = opt.split("=", 1)
        except:
            return super().option_set(opt)
        if k == "dev":
            self.params["dev"] = v
            return self.options_apply()
        if k == "rate":
            self.params["rate"] = int(v)
            return self.options_apply()
        if k == "bits":
            self.params["bits"] = int(v)
            return self.options_apply()
        if k == "parity":
            self.params["parity"] = v[0].upper()
            return self.options_apply()
        if k == "stop":
            self.params["stop"] = int(v)
            return self.options_apply()
        if k == "rtscts":
            self.params["rtscts"] = v.lower() in ["1", "true", "on", "yes"]
            return self.options_apply()
        return super().option_set(opt)

    def options_apply(self):
        if not self.io:
            return
        for k, v in self._options():
            setattr(self.io, k, v)
    
    def _options(self):
        return dict(
            baudrate = self.params["rate"],
            bytesize = self.params["bits"],
            stopbits = self.params["stop"],
            rtscts = self.params["rtscts"],
            parity = self.PARITY_MAP[self.params["parity"].upper()],
        )

    def start(self):
        self.io = serial.Serial(self.params["dev"], **self._options())
        
    def _write(self, data, timeout = None):
        self.adapter.io.timeout = timeout or 60
        self.adapter.io.write(bytes(data))

    def _read(self, size, timeout = None):
        self.adapter.io.timeout = timeout or 60
        if size is None:
            size = self.adapter.io.in_waiting
        if size:
            return bytes(self.adapter.io.read(size))
        return b''

class SerialAdapter(model.Adapter):
    supported_interfaces = ["pipe"]

    def __init__(self, name, dev = None):
        super().__init__(name)
        self.device = dev

    def open(self, name):
        if name == "pipe":
            return SerialInterface(self, self.device)
            
@model.HwRoot.register
class SerialEnumerator(model.Enumerator):
    adapter_class = SerialAdapter
    prefix = "serial"

    def __init__(self):
        super().__init__("serial")
    
    def start(self):
        for port in serial.tools.list_ports.comports():
            adapter = SerialAdapter(port.name, port.device)
            self.child_add(adapter)
        super().start()
