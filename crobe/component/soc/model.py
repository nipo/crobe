from ... import model
from ...db import Db
from ...part_id import PartId

__all__ = ["SoC"]

class SoC(model.Component):
    """
    A SoC component.
    """
    
    db = Db()

    def __init__(self, name):
        model.Component.__init__(self, name)
