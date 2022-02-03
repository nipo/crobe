import logging

class BadInvocation(Exception):
    def __init__(self, message):
        self.__message = message
        Exception.__init__(self, "Bad invocation", message)

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
    def __init__(self, name = None):
        if name is None:
            assert hasattr(self, "name")
        else:
            assert isinstance(name, str)
            self.name = name
        self.__parent = None
        self.__children = []
        self.__started = False

    @property
    def children(self):
        return self.__children[:]

    def start_root(self):
        self.__start()

    def start(self):
        ...

    def __str__(self):
        return str(self.__name)
    
    @property
    def name(self):
        return self.__name

    @property
    def fqdn(self):
        if self.__parent:
            return f'{self.__parent.fqdn}.{self.__name}'
        return self.__name

    @name.setter
    def name(self, name):
        self.__name = name

    @property
    def logger(self):
        return logging.getLogger(self.fqdn)
    
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

    def parent_of_class(self, klass):
        """
        Retrieve children in the parents
        """
        if isinstance(self.__parent, klass):
            return self.__parent
        print(self.__parent)
        return self.__parent.parent_of_class(klass)

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

    def __start(self, recurse = True):
        if not self.__started:
            self.__started = True
            self.start()
        if recurse:
            for child in self.__children:
                child.__start()

    def child_remove(self, obj):
        if obj.__parent is None:
            raise RuntimeError("Object is already dangling")
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

    def child_summon(self, *invocation):
        r = self.__child_summon(*invocation)
        if self.__started:
            r.__start(False)
        return r

    def __child_summon(self, crit = None, *invocation):
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
            child = self.__child_spawn(crit)
            if not child:
                raise BadInvocation(crit)

            # Must apply options before adding to tree (i.e. starting)
            child.__options_apply(options)
            self.child_add(child)

        self.logger.info("Had %s", child)

        if self.__started:
            child.__start(False)
        
        return child.child_summon(*invocation)

    def __child_lookup(self, crit):
        if crit == "..":
            return self.__parent

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
    
    def __child_spawn(self, crit):
        from .db import NoMatch, InitializationFailure
        self.logger.debug("Spawning '%s' on %s", crit, self.__class__.__mro__)
        for cla in self.__class__.__mro__:
            try:
                method = cla.__dict__["child_spawn"]
            except KeyError:
                continue

            self.logger.debug("Trying on '%s'", cla.__name__)

            try:
                return method(self, crit)
            except (NoMatch, InitializationFailure, BadInvocation) as e:
                self.logger.debug(" -> %s", e.__class__.__name__)
                pass
        return None

    def child_spawn(self, crit):
        raise BadInvocation(crit)

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

class Bus32Component(BusComponent):
    def __init__(self, bus, base, name = "Memory Component"):
        super().__init__(bus, name)
        self.base = base

    def reg_read(self, offset):
        op = self.cmd_reg_read(offset)
        self.bus.execute([op])
        return op.data

    def reg_write(self, offset, data):
        op = self.cmd_reg_write(offset, data)
        self.bus.execute([op])

    def cmd_reg_read(self, offset):
        return self.bus.cmd_u32_read(self.base + offset)

    def cmd_reg_write(self, offset, data, interval = 0):
        return self.bus.cmd_u32_write(self.base + offset, data, interval)
