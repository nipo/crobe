
class Memory:
    """
    Memory model for an ISS.
    """
    def load(self, address, bit_size, *, signed = False):
        ...

    def store(self, address, bit_size, value):
        ...
