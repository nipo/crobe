import logging

class BadInvocation(Exception):
    def __init__(self, message):
        self.__message = message
        Exception.__init__(self, "Bad invocation")

    def message_get(self):
        return self.__message

class BadInvocationFormat(Exception):
    def __init__(self, message):
        self.__message = message
        Exception.__init__(self, "Bad invocation formatting")

    def message_get(self):
        return self.__message

class BadOption(Exception):
    def __init__(self, o):
        Exception.__init__(self, "Bad option", o)

    def message_get(self):
        return "option rejected by component"

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
        self.__parent = None
        self.__children = []
        self.__started = False

    @property
    def children(self):
        return self.__children[:]

    def start(self):
        return self.__start()

    def __str__(self):
        return self.__name
    
    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, name):
        self.__name = name
        self.logger = logging.getLogger(name[:10])
    
    def children_find(self, predicate, include_self = False):
        """
        Retrieve children in the deep subtree matching predicate.
        """
        ret = []
        if include_self:
            try:
                if predicate(self):
                    ret.append(self)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
        for c in self.__children:
            try:
                if predicate(c):
                    ret.append(c)
            except Exception as e:
                self.logger.warning("children find predicate exception: %s", e)
            ret += c.children_find(predicate)
        return ret
    
    def children_of_class(self, klass, include_self = False):
        """
        Retrieve children in the deep subtree of class klass.
        """
        return self.children_find(lambda x: isinstance(x, klass), include_self)

    def child_add(self, obj):
        if obj.__parent is self:
            assert obj in self.__children
            return

        assert obj.__parent is None, (obj, obj.__parent)
        assert obj not in self.__children

        obj.__parent = self
        self.__children.append(obj)

        self.logger.info("child_add %s %s %s", obj, self.__started, obj.__started)
        self.children_changed()
        if self.__started:
            obj.__start()

    def __start(self):
        if self.__started:
            return False
        self.__started = True
        self.start()
        for child in self.__children:
            child.__start()
        return True

    def child_remove(self, obj):
        if obj.__parent is None:
            raise RuntimeError("Object is already dandling")
        assert obj.__parent is self, obj.__parent
        obj.__parent = None
        self.__children.remove(obj)
        self.children_changed()

    def children_changed(self):
        pass
        
    def option_set(self, opt):
        self.logger.warning("Option %r ignored", opt)

    def __options_apply(self, options):
        for opt in options:
            try:
                self.option_set(opt)
            except Exception as e:
                raise BadOption(opt) from e

    def child_summon(self, crit = None, *invocation):
        options = []

        self.logger.info("Summon %s %s", crit, invocation)

        if crit and crit.endswith(')'):
            try:
                index = crit.index('(')
            except ValueError:
                raise BadInvocationFormat("Unmatched parenthesis in \"%s\"" % (crit,))
            options = crit[index + 1 : -1].split(",")
            crit = crit[: index]

        if not crit and not invocation:
            return self
        
        child = self.__child_lookup(crit)
        if child:
            child.__options_apply(options)
        else:
            child = self.child_spawn(crit)
            if not child:
                raise BadInvocation(crit)

            # Must apply options before adding to tree (i.e. starting)
            child.__options_apply(options)
            self.child_add(child)

        self.logger.info("Had %s", child)
            
        return child.child_summon(*invocation)

    def __child_lookup(self, crit):
        if crit == "*" and len(self.__children) == 1:
            return self.__children[0]

        try:
            index = int(crit)
        except ValueError:
            index = None

        if index is not None:
            return self.__children[index]

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
