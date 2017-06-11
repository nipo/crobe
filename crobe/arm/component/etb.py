from .model import CoresightComponent

@CoresightComponent.db.register(0x21)
class Etb(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base)

    def __str__(self):
        return "Embedded Trace Buffer"
