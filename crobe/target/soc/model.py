from .. import model
from ...part_id import PartId
from ...memory import region

__all__ = ["SoC"]

class SoC(model.Target):
    """
    A SoC component.
    """

    def __init__(self, name):
        model.Target.__init__(self, name)
        self.uid = 0

    def load(self, program):
        regions = self.children_of_class(region.Region)
        for r in regions:
            if not isinstance(r, region.Flash):
                continue

            pages = program.within(r.address, r.address + r.size)
            r.erase(pages.address, pages.end - pages.address)
            r.write(pages)
