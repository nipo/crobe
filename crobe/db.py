import operator

__all__ = ["Db", "NoMatch"]

class NoMatch(Exception):
    pass

class Db(object):
    def __init__(self, eq_func = operator.eq):
        self.registry = {}
        self.eq_func = eq_func
        self.default = None

    def register(self, *id):
        return lambda x: self._register(id, x)

    def register_default(self, obj):
        self.default = obj

    def _register(self, ids, obj):
        for i in set(ids):
            if i not in self.registry:
                self.registry[i] = [obj]
            else:
                self.registry[i].append(obj)
        return obj

    def get(self, id, allow_default = True):
        for k in self.registry.keys():
            if self.eq_func(k, id):
                return self.registry[k]

        if self.default is not None and allow_default:
            return [self.default]

        raise NoMatch(id)

    def call(self, id, *args, allow_default = True):
        poss = self.get(id, allow_default = allow_default)
        
        for i, f in enumerate(poss):
            try:
                return f(*args)
            except NoMatch:
                pass

        if self.default is not None and allow_default:
            return self.default(*args)

        raise NoMatch(id)
