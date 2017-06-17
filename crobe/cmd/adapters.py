def main():
    from . import base
    from ..adapter.model import Enumerator, Adapter
    
    class Tool(base.Command):
        pass

    args = Tool("Adapter list")

    Enumerator.singleton.start()

    enumerator_dump(Enumerator.singleton)

def enumerator_dump(e, prefix = ""):
    from ..adapter.model import Enumerator, Adapter

    print(prefix + "* Enumerator", e)

    prefix += "  "

    for c in e.children:
        if isinstance(c, Enumerator):
            enumerator_dump(c, prefix)
        elif isinstance(c, Adapter):
            print(prefix + "* Adapter", c, "supported interfaces:", *c.supported_interfaces)
        else:
            print(prefix + "* ????", c)

if __name__ == '__main__':
    main()


