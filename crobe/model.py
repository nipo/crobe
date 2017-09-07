import logging
import weakref

class Component(object):
    """
    Crobe base component.  Everything in crobe is a component
    (Enumerators, Adapters, Interfaces, TAPs, Debug components, SoCs,
    etc.).

    Components are hierarchical, they can have children.

    There are utilities to retrieve a component in the subtree of an
    other.
    """
    def __init__(self, name):
        self.name = name
        self.children = []
        self.__started = False

    def start(self):
        assert not self.__started
        self.__started = True
        
        for c in self.children[:]:
            c.start()
        
    def __str__(self):
        return self.__name

    @property
    def started(self):
        return self.__started
    
    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, name):
        self.__name = name
        self.logger = logging.getLogger(name[:10])
    
    def children_find(self, predicate, include_self = False):
        """
        Retrieve childrens in the deep subtree matching predicate.
        """
        ret = []
        if include_self:
            try:
                if predicate(self):
                    ret.append(self)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
        for c in self.children:
            try:
                if predicate(c):
                    if isinstance(c, weakref.ProxyTypes):
                        c = c.ref()
                    ret.append(c)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
            ret += c.children_find(predicate)
        return ret
    
    def children_of_class(self, klass, include_self = False):
        """
        Retrieve childrens in the deep subtree of class klass.
        """
        return self.children_find(lambda x: isinstance(x, klass), include_self)

    def child_add(self, obj, weak = False):
        if weak:
            obj = weakref.proxy(obj, self.weak_child_cleanup)
        self.children.append(obj)

    def child_remove(self, obj):
        self.children.remove(obj)

    def weak_child_cleanup(self, proxy):
        for i in range(len(self.children)-1, -1, -1):
            try:
                self.children[i]
            except ReferenceError:
                del self.children[i]

    def option_set(self, opt):
        self.logger.warning("Option %r ignored", opt)

    def child_summon(self, crit = None, *invocation):
        if not self.__started:
            self.start()

        options = []

        self.logger.info("Summon %s", crit)

        if crit and crit.endswith(')'):
            try:
                index = crit.index('(')
            except ValueError:
                raise ValueError("Unmatched parenthesis", crit)
            options = crit[index + 1 : -1].split(",")
            crit = crit[: index]
            
        if not crit and not invocation:
            return self

        child = self.child_lookup(crit) or self.child_spawn(crit)

        if not child:
            raise ValueError("Unknown invocation", crit, *invocation)

        for opt in options:
            child.option_set(opt)

        self.logger.info("Had %s", child)
            
        return child.child_summon(*invocation)

    def child_lookup(self, crit):
        if crit == "*" and len(self.children) == 1:
            return self.children[0]

        try:
            index = int(crit)
            return self.children[index]
        except ValueError:
            pass

        possible = self.children_find(lambda x:crit.lower() in x.name.lower())
        if len(possible) == 1:
            return possible[0]
    
    def child_spawn(self, crit):
        return None

class BusComponent(Component):
    """
    Component with a bus interface.
    """

    def __init__(self, bus, name):
        Component.__init__(self, name)
        self.bus = bus

class PortComponent(Component):
    """
    Component with a port interface.
    """

    def __init__(self, port, name):
        Component.__init__(self, name)
        self.port = port
