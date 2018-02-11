from .model import CoresightComponent
from ....part_id import PartId

@CoresightComponent.db.register(
    0x16, # a9 PMU
    )
class Pmu(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base, "Performance Monitoring Unit")

