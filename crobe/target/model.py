from .. import model
import operator
import functools
from ..protocol import swd, jtag

class Explorer(object):
    def __init__(self, func, component_types, precedence):
        self.func = func
        self.component_types = component_types
        self.precedence = precedence

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __lt__(self, other):
        return self.precedence < other.precedence

    def __lte__(self, other):
        return self.precedence <= other.precedence
    
class Field(model.Component):

    def __init__(self):
        model.Component.__init__(self, "Targets")

    def discover(self, interface):
        interface.start_root()

        types = set()
        for e in Target.registry:
            types |= set(e.component_types)

        interests = {}
        for t in types:
            interests[t] = set(interface.children_of_class(t, True))

        handled = set()
            
        for explorer in Target.registry:
            for comp_type in explorer.component_types:
                for component in interests[comp_type]:
                    try:
                        target = explorer(component)
                    except NotImplementedError:
                        continue

                    self.child_add(target)

                    to_remove = set(component.children_find(lambda x:True))

                    for k in interests.keys():
                        interests[k] -= to_remove

        self.unhandled = functools.reduce(operator.__or__, interests.values(), set())
        
class Target(model.Component):
    registry = []
    
    @classmethod
    def register(cls, *component_types, precedence = 1000):
        return lambda func: cls._register(func, component_types, precedence)

    @classmethod
    def _register(cls, func, component_types, precedence):
        cls.registry.append(Explorer(func, component_types, precedence))
        cls.registry.sort()
        return func

    def __init__(self, name):
        model.Component.__init__(self, name)
