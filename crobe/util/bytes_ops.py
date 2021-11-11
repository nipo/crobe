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
    return bytes_map(operator.or_, a, b)

def and_(a, b):
    return bytes_map(operator.and_, a, b)

def xor_(a, b):
    return bytes_map(operator.xor_, a, b)

def not_(a):
    return bytes_map(operator.xor_, a, 0xff)
