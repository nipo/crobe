def prime_factors(n):
    i = 2
    factors = []
    while i * i <= n:
        if n % i:
            i += 1
        else:
            n //= i
            factors.append(i)
    if n > 1:
        factors.append(n)
    if not factors:
        return [n]
    return factors

def prime_map(n):
    ret = {}
    for i in prime_factors(int(n)):
        if i in ret:
            ret[i] += 1
        else:
            ret[i] = 1
    return ret

def integer_ratio(source, destination):
    source_factors = prime_map(source)
    destination_factors = prime_map(destination)

    ratio_factors = dict(destination_factors.items())
    for p, c in source_factors.items():
        if p in ratio_factors:
            ratio_factors[p] -= c
        else:
            ratio_factors[p] = -c

    num = []
    denom = []
    for p, c in ratio_factors.items():
        if c > 0:
            num.extend([p] * c)
        if c < 0:
            denom.extend([p] * -c)

    return num, denom
