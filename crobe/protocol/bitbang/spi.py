from .. import spi
from .bitbang import Mode, IoConfig, IoSet, IoGet, Interface

@Interface.db.register("spi")
class SpiInterface(spi.Interface):
    def __init__(self, port):
        super().__init__(port, "spi")
        self.mosi = None
        self.miso = None
        self.sck = None
        self.cs0 = None
        self.hi = []
        self.lo = []
        self.child_add(spi.Target(self, "cs0", 0))

    def freq_update(self, freq):
        return self.port.freq_cap("spi", freq or 1200e3)

    def start(self):
        if not self.sck:
            raise ValueError("Should set sck at least")

        for port in self.hi:
            self.port.set(IoConfig(port, value = True, mode = Mode.D0D1))
        for port in self.lo:
            self.port.set(IoConfig(port, value = False, mode = Mode.D0D1))

        if self.cs0:
            self.port.set(IoConfig(self.cs0, value = True, mode = Mode.D0Z1))
        if self.mosi:
            self.port.set(IoConfig(self.mosi, value = False, mode = Mode.D0D1))
        if self.miso:
            self.port.set(IoConfig(self.miso, value = False, mode = Mode.Input))
        if self.sck:
            self.port.set(IoConfig(self.sck, value = False, mode = Mode.D0D1))
        
    def option_set(self, opt):
        if opt.startswith("mosi="):
            self.mosi = opt[5:]
            return
        if opt.startswith("miso="):
            self.miso = opt[5:]
            return
        if opt.startswith("cs0="):
            self.cs0 = opt[4:]
            return
        if opt.startswith("sck="):
            self.sck = opt[4:]
            return
        if opt.startswith("hi="):
            self.hi = opt[3:].split(";")
            return
        if opt.startswith("lo="):
            self.lo = opt[3:].split(";")
            return
        super().option_set(opt)

    def _op_shift_byte(self, byte_value, read):
        ops = []
        for i in range(8):
            mosi = (byte_value >> 7) & 1
            byte_value <<= 1

            if self.mosi is not None:
                ops.append(IoSet(IoConfig(self.mosi, value = mosi),
                                 IoConfig(self.sck, value = False)))
            else:
                ops.append(IoSet(IoConfig(self.sck, value = False)))

            ops.append(IoSet(IoConfig(self.sck, value = True)))
            if self.miso is not None:
                ops.append(IoGet([self.miso]))
        return ops

    def _op_shift_gather(self, ops):
        bit = 7
        ret = []
        tmp = 0

        for o in ops:
            if isinstance(o, IoGet):
                value, = o.values.values()
                tmp |= int(bool(value)) << bit
                bit -= 1
                if bit < 0:
                    bit = 7
                    ret.append(tmp)
                    tmp = 0
        return bytes(ret)
                
    def _execute(self, operation_list):
        pending = []
        rx_map = {}

        for index, op in enumerate(operation_list):
            if isinstance(op, spi.Cs):
                if self.cs0 is None:
                    continue

                pending.append(IoSet(IoConfig(self.sck, value = False)))
                pending.append(IoSet(IoConfig(self.cs0, value = op.value is None)))
                pending.append(IoSet(IoConfig(self.sck, value = False)))
                continue

            if isinstance(op, spi.Shift):
                offset_pre = len(pending)

                if isinstance(op.mosi, int):
                    for i in range(op.mosi):
                        pending += self._op_shift_byte(0x00, read = op.read_miso)
                else:
                    for b in op.mosi:
                        pending += self._op_shift_byte(b, read = op.read_miso)
                offset_post = len(pending)

                if op.read_miso:
                    assert self.miso is not None
                    rx_map[index] = offset_pre, offset_post

        self.port.execute(pending)

        for index, op in enumerate(operation_list):
            if not isinstance(op, spi.Shift) or not op.read_miso:
                continue

            pre, post = rx_map[index]
            op.miso = bytes(self._op_shift_gather(pending[pre:post]))
        
                    
