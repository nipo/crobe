from .. import model
from ...part_id import PartId
from ...memory import region
from .. import loadable

__all__ = ["SoC"]

class SoC(model.Target, loadable.Loadable):
    """
    A SoC component.
    """

    def __init__(self, name):
        model.Target.__init__(self, name)
        self.uid = 0

    def load(self, program, erase = True):
        regions = self.children_of_class(region.Region)
        for r in regions:
            if not isinstance(r, region.Flash):
                continue

            pages = program.within(r.address, r.address + r.size)
            if erase:
                r.erase(pages.address - r.address, pages.end - pages.address)
            r.load(pages)

    def verify(self, program):
        regions = self.children_of_class(region.Region)
        for r in regions:
            if not isinstance(r, region.Flash):
                continue

            pages = program.within(r.address, r.address + r.size)
            if not r.verify(pages):
                return False
        return True
