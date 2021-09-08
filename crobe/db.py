import operator

__all__ = ["Db", "NoMatch", "InitializationFailure"]

class NoMatch(Exception):
    def __init__(self, db_name, criterion):
        self.db_name = db_name
        self.criterion = criterion

    def message_get(self):
        return "Unable to find '%s' in %s" % (self.criterion, self.db_name)

class InitializationFailure(Exception):
    def message_get(self):
        return "Unable to initialize component"

class Db(object):
    def __init__(self, db_name, eq_func = operator.eq):
        self.db_name = db_name
        self.registry = {}
        self.eq_func = eq_func
        self.default = None

    def register(self, *id):
        return lambda x: self._register(id, x)

    def register_default(self, obj):
        self.default = obj
        return obj

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

        raise NoMatch(self.db_name, id)

    def call(self, id, *args, allow_default = True, **kwargs):
        poss = self.get(id, allow_default = allow_default)
        exc = []
        
        for i, f in enumerate(poss):
            try:
                return f(*args, **kwargs)
            except NoMatch as e:
                exc.append(e)
            except InitializationFailure as e:
                exc.append(e)
            except Exception as e:
                exc.append(e)

        if self.default is not None and allow_default:
            return self.default(*args, **kwargs)

        if len(exc) == 1:
            raise NoMatch(self.db_name, id) from exc[0]
        raise NoMatch(self.db_name, id)
