import logging

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

    def child_add(self, obj):
        self.children.append(obj)
    
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
