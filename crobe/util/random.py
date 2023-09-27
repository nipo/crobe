__all__ = ["random_data"]

def random_data(size):
    with open("/dev/urandom", "rb") as fd:
        ret = b''
        while len(ret) < size:
            ret += fd.read(size - len(ret))
        return ret
