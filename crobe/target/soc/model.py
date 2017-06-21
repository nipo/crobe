from .. import model
from ...part_id import PartId

__all__ = ["SoC"]

class SoC(model.Target):
    """
    A SoC component.
    """

    def __init__(self, name):
        model.Target.__init__(self, name)
