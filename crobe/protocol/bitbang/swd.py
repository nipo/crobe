from .. import swd
from .bitbang import Mode, IoInput, IoPushPull, Interface

@Interface.db.register("swd")
class SwdInterface(swd.Interface):
    def __init__(self, port):
        super().__init__(port, "swd")
        self.swdio = None
        self.swclk = None
        self.hi = []
        self.lo = []

    def freq_update(self, freq):
        return self.port.freq_cap("swd", freq * 2 if freq is not None else None) / 2
        
    def start(self):
        if not self.swdio or not self.swclk:
            raise ValueError("Should set swdio/swclk options")

        for port in self.hi:
            self.port.set(IoPushPull(port, value = True))
        for port in self.lo:
            self.port.set(IoPushPull(port, value = False))
            
        self.port.set(IoPushPull(self.swclk, value = True),
                      IoInput(self.swdio, value = True))

        super().start()
        
    def option_set(self, opt):
        if opt.startswith("swdio="):
            self.swdio = opt[6:]
            return
        if opt.startswith("swclk="):
            self.swclk = opt[6:]
            return
        if opt.startswith("hi="):
            self.hi = opt[3:].split(",")
            return
        if opt.startswith("lo="):
            self.lo = opt[3:].split(",")
            return
        super().option_set(opt)

    def _out(self, value = None):
        mode = Mode.D0D1 if value is not None else Mode.Input
        return [
            self.port.cmd_set(IoPushPull(self.swclk, value = False),
                              IoConfig(self.swdio, value = value, mode = mode)),
            self.port.cmd_set(IoPushPull(self.swclk, value = True)),
        ]

    def _in(self):
        return [
            self.port.cmd_set(IoPushPull(self.swclk, value = False),
                              IoInput(self.swdio, value = None)),
            self.port.cmd_get([self.swdio]),
            self.port.cmd_set(IoPushPull(self.swclk, value = True)),
        ]
        
    def _swd_wakeup(self, cycles = 50):
        self.port.execute(self._out(True) * cycles)

    def _swd_run(self, cycles):
        self.port.execute(self._out(False) * cycles)

    def _swd_select(self, out):
        ops = []
        for b in range(len(out)):
            ops += self._out(out[b])
        self.port.execute(ops)

    def _swd_rw(self, cmd, turn, data = None):
        ops = []
        ops += self._out(False)
        for b in range(8):
            ops += self._out((cmd >> b) & 1)
        ops += self._out(None) * turn
        a_index = len(ops) + 1
        ops += self._in()
        ops += self._in()
        ops += self._in()

        if data is not None:
            ops += self._out(None) * turn

            p = False
            for i in range(32):
                bit = (data >> i) & 1
                p ^= bit
                ops += self._out(bit)
            ops += self._out(p)
            ops += self._out(False)

            self.port.execute(ops)

            ack = 0
            for i, ii in enumerate(range(a_index, a_index + 9, 3)):
                if ops[ii].values[self.swdio]:
                    ack |= 1 << i

            return ack

        else:
            for d in range(33):
                ops += self._in()
            ops += self._out(None) * turn
            ops += self._out(False)

            self.port.execute(ops)

            ack = 0
            for i, ii in enumerate(range(a_index, a_index + 9, 3)):
                if ops[ii].values[self.swdio]:
                    ack |= 1 << i
            data = 0
            for i, ii in enumerate(range(a_index + 3 * 3, a_index + 3 * 35, 3)):
                if ops[ii].values[self.swdio]:
                    data |= 1 << i

            par = int(ops[a_index + 3 * 35].values[self.swdio])

            return ack, data, par

    def _execute(self, operation_list):
        for op in operation_list:
            if isinstance(op, swd.Read):
                ack, data, par = self._swd_rw(op.cmd, self.turnaround_cycles)

                pdata = data ^ (data >> 16)
                pdata ^= (pdata >> 8)
                pdata ^= (pdata >> 4)
                pdata = (0x6996 >> (pdata & 0xf)) & 1
                if pdata != par:
                    ack = swd.Ack.PARITY_ERR
                else:
                    ack = swd.Ack(ack)
                op.ack = ack
                op.data = data

                if op.ap:
                    self._swd_run(10)
                
                continue

            if isinstance(op, swd.Write):
                ack = self._swd_rw(op.cmd, self.turnaround_cycles, op.data)
                op.ack = swd.Ack(ack)

                if op.ap:
                    self._swd_run(10)

                continue

            if isinstance(op, swd.SelectionOperation):
                self._swd_select(op.out)
                continue

            if isinstance(op, swd.Wakeup):
                self._swd_wakeup(op.cycles)
                continue
            
            if isinstance(op, swd.Run):
                self._swd_run(op.cycles)
                continue

            if isinstance(op, base.Reset):
                self.logger.warning("Reset operation ignored")
                continue

            raise ValueError(op)
