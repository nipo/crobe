
__all__ = ["Db", "NoMatch"]

class NoMatch(Exception):
    pass

class Db(object):
    def __init__(self, id_filter = lambda x:x):
        self.registry = {}
        self.id_filter = id_filter
        self.default = None

    def register(self, *id):
        return lambda x: self._register(id, x)

    def register_default(self, obj):
        self.default = obj

    def _register(self, ids, obj):
        for i in set(map(self.id_filter, ids)):
            if i not in self.registry:
                self.registry[i] = [obj]
            else:
                self.registry[i].append(obj)
        return obj

    def get(self, id):
        fid = self.id_filter(id)

        if self.default is not None:
            return self.registry.get(fid, [self.default])
        try:
            return self.registry[fid]

        except KeyError:
            raise NoMatch(id)

    def call(self, id, *args, **kwargs):
        poss = self.get(id)

        for i, f in enumerate(poss):
            try:
                return f(*args, **kwargs)
            except NoMatch:
                pass

        if self.default is not None:
            return self.default(*args, **kwargs)

        raise NoMatch(id)
