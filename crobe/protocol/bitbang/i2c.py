from .. import i2c
from .bitbang import Mode, IoOp, Interface

@Interface.db.register("i2c")
class I2cInterface(i2c.Interface):
    def __init__(self, port):
        super().__init__(port, "i2c")
        self.sda = None
        self.scl = None

    def freq_update(self, freq):
        return freq or 0
        
    def start(self):
        if not self.sda or not self.scl:
            raise ValueError("Should set sda/scl options")

        self.port.set(IoOp(self.scl, value = True, mode = Mode.D0Z1),
                      IoOp(self.sda, value = True, mode = Mode.D0Z1))
        
    def option_set(self, opt):
        if opt.startswith("sda="):
            self.sda = opt[4:]
            return
        if opt.startswith("scl="):
            self.scl = opt[4:]
            return
        super().option_set(opt)

    def _set(self, scl, sda):
        self.port.set(IoOp(self.scl, value = scl),
                      IoOp(self.sda, value = sda))
        
    def _get(self):
        return self.port.get(self.scl, self.sda)

    def _start(self):
        self.logger.debug("Start")
        self._set(1, 1)
        self._set(1, 0)
        self._set(0, 0)

    def _stop(self):
        self.logger.debug("Stop")
        self._set(0, 0)
        self._set(1, 0)
        self._set(1, 1)

    def _shift_bit(self, sda):
        self._set(0, sda)
        self._set(1, sda)
        c, d = self._get()
        self._set(0, sda)
        return d

    def _shift_byte(self, data = 0xff, nack = 1):
        self.logger.debug("Shift byte 0x%02x, nack %d", data, int(nack))
        d = 0
        for i in range(7, -1, -1):
            d <<= 1
            d |= self._shift_bit((data >> i) & 1)
        a = self._shift_bit(nack)
        self.logger.debug(" -> 0x%02x, nack %d", d, int(a))
        return d, a
    
    def _execute(self, operation_list):
        operation_list = list(operation_list)
        prev = None
        first = False

        try:
            for idx, op in enumerate(operation_list):
                as_prev = bool(prev) and isinstance(prev, i2c.Read) == isinstance(op, i2c.Read)

                if isinstance(op, i2c.Read):
                    is_last = idx == len(operation_list)-1 or not isinstance(operation_list[idx], i2c.Read)
                    if not as_prev:
                        self._start()
                        _, nack = self._shift_byte(data = (op.addr << 1) | 1)
                        if nack:
                            raise i2c.AddressNack(op.addr)
                    data = []
                    for d in range(op.size):
                        d, _ = self._shift_byte(data = 0xff, nack = is_last and d == op.size-1)
                        data.append(d)
                    op.data = bytes(data)

                elif isinstance(op, i2c.Write):
                    if not as_prev:
                        self._start()
                        _, nack = self._shift_byte(data = op.addr << 1)
                        if nack:
                            raise i2c.AddressNack(op.addr)
                    for d in range(op.data):
                        _, nack = self._shift_byte(data = d)
                        if nack:
                            raise i2c.DataNack()
        finally:
            self._stop()
