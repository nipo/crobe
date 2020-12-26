from ..model import PortComponent
from ..protocol import spi
import binascii

__all__ = ["JtagSpiBridge"]

class SpiInterface(spi.Interface):
    def __init__(self, port, base_freq):
        from .nsl.transactor.spi import SpiTransactor
        self.__spi = SpiTransactor(port, base_freq)
        super().__init__(port, "spi")
        self.child_add(spi.Target(self, "cs0", 0))

    def execute(self, op_list):
        self.__spi.execute(op_list)

    def freq_update(self, freq):
        return self.__spi.freq_update(freq)

class JtagSpiBridge(PortComponent):
    def __init__(self, port, data_io, status_io, base_freq):
        from .nsl.bnoc import jtag_fifo_transport, framed

        self.__fifo = jtag_fifo_transport.JtagFifoTransport(port, 9, data_io, status_io)
        self.__base_freq = base_freq
        self.__gateway = framed.Framed(self.__fifo)

        super().__init__(port, "bridge")
        self.spi = SpiInterface(self.__gateway, base_freq)
        self.child_add(self.spi)
