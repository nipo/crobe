from decimal import Decimal

def metric(value, unit = "", ascii = False):
    if isinstance(value, (int, float)):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        return value
    if value == 0:
        return "0"

    if value < 0:
        value = -value
        s = "-"
    else:
        s = ""
    exp = 0
    if value < 1:
        while value * Decimal((0, (1,), exp)) < 1:
            exp += 3
    else:
        while value * Decimal((0, (1,), exp)) >= 1000:
            exp -= 3
    m = value * Decimal((0, (1,), exp))
    scale = "TGMk munpf" if ascii else u"TGMk mµnpf"
    suffix = scale[4 + exp // 3]
    if suffix == ' ':
        suffix = ''
    return s + ('%f' % (int(float(m * 1000) + .5) // 1000.)).rstrip('0').rstrip('.') + suffix + unit

def base2(value, unit = ""):
    if value <= 1:
        return str(value) + unit

    if isinstance(value, (int, float, Decimal)):
        value = int(value)
        
    exp = 0
    while (value >> exp) >= 1024:
        exp += 10
    m = value * (2. ** -exp)
    scale = " kMGT"
    suffix = scale[exp // 10]

    if suffix == ' ':
        suffix = ''

    return ('%f' % (int(float(m * 1024) + .5) // 1024.)).rstrip('0').rstrip('.') + suffix + "i" + unit

def sci_parse(string):
    suffix = {
        "T": 12,
        "G": 9,
        "M": 6,
        "k": 3,
        "K": 3,
        " ": 0,
        "m": -3,
        u"µ": -6,
        "u": -6,
        "n": -9,
        "p": -12,
        "f": -15,
    }

    assert string

    if string[-1] in suffix:
        exp = suffix[string[-1]]
        string = string[:-1]
    else:
        exp = 0
    return (Decimal(string) * Decimal((0, (1,), exp)))
