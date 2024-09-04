from . import model
import serial
import serial.tools.list_ports
from ..protocol import pipe
import threading
import time
import os
import os.path

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
            xonxoff = False,
        )
        self.io = None
        pipe.BackgroundInterface.__init__(self, adapter, adapter.name)

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
        if k == "xonxoff":
            self.params["xonxoff"] = v.lower() in ["1", "true", "on", "yes"]
            return self.options_apply()
        return super().option_set(opt)

    def options_apply(self):
        if not self.io:
            return
        for k, v in self._options().items():
            setattr(self.io, k, v)
            self.logger.info(f"Set {k} = {v}")
        self.io.timeout = .1
    
    def _options(self):
        return dict(
            baudrate = int(self.params["rate"]),
            bytesize = self.params["bits"],
            stopbits = self.params["stop"],
            rtscts = self.params["rtscts"],
            xonxoff = self.params["xonxoff"],
            parity = self.PARITY_MAP[self.params["parity"].upper()],
        )

    def start(self):
        self.io = serial.Serial(self.params["dev"], **self._options())
        self.options_apply()
        super().start()
        
    def _write(self, data, timeout = None):
        start = time.time()
        written = 0
        while data:
            self.logger.protocol("< %s", data.hex())
            w = self.io.write(bytes(data))
            data = data[w:]
            written += w
            elapsed = time.time() - start
            if timeout and elapsed > timeout:
                break
        return written

    def _read(self, size, timeout = None):
        self.logger.protocol("> size %s timeout %s", size, timeout)

        deadline = time.time() + timeout
        data = b''

        while True:
            if size is None:
                d = bytes(self.io.read(self.io.in_waiting or 1))
            else:
                left = size - len(data)
                if left <= 0:
                    break
                d = bytes(self.io.read(left))
            self.logger.protocol(">* %s", d.hex())
            data += d
            if d:
                deadline = time.time() + timeout
            if timeout is not None and time.time() > deadline:
                break
        self.logger.protocol("> %s", data.hex())
        return data

    def rts_set(self, value):
        self.io.setRTS(value)

    def rts_get(self):
        return self.io.getRTS()
    
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
            if port.name:
                name = port.name
            else:
                name = os.path.basename(str(port.device))
            adapter = SerialAdapter(name, port.device)
            self.child_add(adapter)
        super().start()
