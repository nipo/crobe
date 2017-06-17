from . import model
from .ftdi.basic import JtagAdapterEnumerator

__all__ = []

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Digilent HS2", "hs2",
                                       vid = 0x0403, pid = 0x6014, channel = "A",
                                       gpio_output = 0xe0, gpio_value = 0xe0)
