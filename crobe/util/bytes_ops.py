import operator

def bytes_map(op, a, b):
    if not isinstance(a, (bytes, bytearray)):
        raise TypeError("LHS type is not handled")

    if isinstance(b, (bytes, bytearray)):
        if len(a) != len(b):
            raise ValueError("Both arguments are not of same length")

        return bytes([op(x, y) for (x, y) in zip(a, b)])
    if isinstance(b, int):
        return bytes([op(x, b) for x in a])
    raise TypeError("RHS type is not handled")

def or_(a, b):
    return bytes_map(operator.__or__, a, b)

def and_(a, b):
    return bytes_map(operator.__and__, a, b)

def xor_(a, b):
    return bytes_map(operator.__xor__, a, b)

def not_(a):
    return bytes_map(operator.__xor__, a, 0xff)
