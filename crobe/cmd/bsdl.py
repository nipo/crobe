from ..part_id import PartId
from ..bsdl.cache import Cache
import glob

def main():
    from . import base
    
    class Tool(base.Command):
        def c25_cache_declare(self):
            self.parser.add_argument("--list", help = "List cache", action = "store_true")
            self.parser.add_argument("--rebuild", help = "Rebuild cache", action = "store_true")
            self.parser.add_argument("--id", help = "Filter by IDCODE", type = str, metavar = "IDCODE")
            self.parser.add_argument("--name", help = "Filter by name", type = str, metavar = "NAME")
            self.parser.add_argument("--pkg", help = "Filter by package", type = str, metavar = "PKG")
            self.parser.add_argument("--dump", help = "Dump component", action = "store_true")

        def c25_cache_parse(self, args):
            self.list = args.list
            self.rebuild = args.rebuild
            self.id = args.id
            self.name = args.name
            self.pkg = args.pkg
            self.dump = args.dump

    args = Tool("BSDL cache manipulation")

    cache = Cache.open()
    if args.rebuild:
        cache.rebuild()
        return

    for entity in cache.filter(name = args.name or None,
                               idcode = int(args.id, 16) if args.id else None,
                               package = args.pkg or None):
        if args.list:
            print("- %s/%s: %s" % (entity.name, entity.package_variant,
                                   [PartId.from_idcode(c.value).pretty() for c in entity.id_codes]))

        if args.dump:
            entity.pprint()

if __name__ == "__main__":
    main()
