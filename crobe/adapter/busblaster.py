from . import model
from .ftdi.basic import JtagAdapterEnumerator

__all__ = []

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Busblaster",
                                       short_name = "bb",
                                       vid = 0x0403, pid = 0x6010, channel = "B",
                                       gpio_output = 0x00, gpio_value = 0x00)
