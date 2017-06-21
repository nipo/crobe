from ...model import Component, Cpu

__all__ = []

class Cortex(Cpu):
    def __init__(self, index, scs, fpb, dwt):
        Cpu.__init__(self, scs.cpu_name, index)
        self.scs = scs
        self.dwt = dwt
        self.fpb = fpb

def cpu_for(index, scs, fpb, dwt):
    return Cortex(index, scs, fpb, dwt)

        
