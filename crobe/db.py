
__all__ = ["Db"]

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
        for i in ids:
            self.registry[self.id_filter(i)] = obj
        return obj

    def get(self, id):
        if self.default is not None:
            return self.registry.get(self.id_filter(id), self.default)
        else:
            return self.registry[self.id_filter(id)]

