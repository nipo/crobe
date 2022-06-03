from ... import model as target_model
from .. import model
from ....component.riscv.dm import DebugModule
from ....db import Db

__all__ = ["SoC"]

class SoC(model.SoC):
    db = Db("SoC model")

    def __init__(self, name, port):
        model.SoC.__init__(self, name)
        self.port = port

@SoC.db.register_default
def default_soc(dm):
    return SoC("Risc-V unknown SoC", dm)

@target_model.Target.register(DebugModule)
def riscv_tap_probe(dm):
    return SoC.db.call(dm.idcode, dm)
