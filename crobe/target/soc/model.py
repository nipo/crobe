from .. import model
from ...part_id import PartId
from .. import memory

__all__ = ["SoC"]

class SoC(model.Target, memory.Loadable):
    """
    A SoC component.
    """

    def __init__(self, name):
        model.Target.__init__(self, name)
        memory.Loadable.__init__(self)
        self.uid = 0
