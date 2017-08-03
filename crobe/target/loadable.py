
class Loadable:
    def read(self, address, size):
        pass

    def erase_all(self):
        pass

    def write(self, program, erase_first = True, verify = False):
        pass

    def verify(self, program):
        pass
