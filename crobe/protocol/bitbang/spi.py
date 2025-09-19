from .. import spi
from .bitbang import IoOpenDrain, IoPushPull, IoInput, Interface, IoGet

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
        self.__mode = 0
        self.child_add(spi.Target(self, "cs0", 0))

    def freq_update(self, freq):
        return self.port.freq_cap("spi", (freq or 1200e3) * 2) / 2

    def start(self):
        if not self.sck:
            raise ValueError("Should set sck at least")

        inits = {port:IoPushPull(value = True) for port in self.hi}
        inits.update({port:IoPushPull(value = False) for port in self.lo})

        if self.cs0:
            inits.update({self.cs0:IoOpenDrain(value = True)})
        if self.mosi:
            inits.update({self.mosi:IoInput()})
        if self.miso:
            inits.update({self.miso:IoInput()})
        if self.sck:
            inits.update({self.miso:IoPushPull(False)})

        self.port.set(inits)
            
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

            if not self.__cpha:
                update_edge = {self.sck: IoPushPull(value = self.__cpol)}

                if self.mosi is not None:
                    update_edge[self.mosi] = IoPushPull(value = mosi)

                ops.append(self.port.cmd_set(update_edge))
                ops.append(self.port.cmd_set({self.sck: IoPushPull(value = not self.__cpol)}))
                if self.miso is not None and read:
                    ops.append(self.port.cmd_get([self.miso]))
            else:
                update_edge = {self.sck: IoPushPull(value = not self.__cpol)}
                if self.mosi is not None:
                    update_edge[self.mosi] = IoPushPull(value = mosi)

                ops.append(self.port.cmd_set(update_edge))
                ops.append(self.port.cmd_set({self.sck: IoPushPull(value = self.__cpol)}))
                if self.miso is not None and read:
                    ops.append(self.port.cmd_get([self.miso]))

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

    @property
    def __cpol(self):
        return bool(self.__mode & 2)

    @property
    def __cpha(self):
        return bool(self.__mode & 1)
    
    def _execute(self, operation_list):
        pending = []
        rx_map = {}

        for index, op in enumerate(operation_list):
            if isinstance(op, spi.Cs):
                self.__mode = op.mode
                ios = {self.sck: IoPushPull(value = self.__cpol)}
                if self.mosi is not None:
                    ios[self.mosi] = IoInput() if op.value is None else IoPushPull(value = False)
                    pending.append(self.port.cmd_set(ios))
                if self.cs0 is not None:
                    ios[self.cs0] = IoOpenDrain(value = not(op.value == 0))
                pending += [self.port.cmd_set(ios)]*8

            elif isinstance(op, spi.Shift):
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
        
                    
