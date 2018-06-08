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
        self.__attached = False

    @property
    def attached(self):
        return self.__attached

    def detach(self):
        if not self.__attached:
            return
        self.__attached = False

    def attach(self):
        if self.__attached:
            return
        self.__attached = True

