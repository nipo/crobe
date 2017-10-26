from .. import config
from ..part_id import PartId
from ..bsdl.cache import Cache
import glob

def main():
    from . import base
    
    class Tool(base.Command):
        def c25_cache_declare(self):
            self.parser.add_argument("--list", help = "List cache", action = "store_true")
            self.parser.add_argument("--rebuild", help = "Rebuild cache", action = "store_true")
            self.parser.add_argument("--id", help = "Find definition by IDCODE", type = str, metavar = "IDCODE")

        def c25_cache_parse(self, args):
            self.list = args.list
            self.rebuild = args.rebuild
            self.id = args.id

    args = Tool("BSDL cache manipulation")

    cache = Cache(config.path_get("cache", "bsdl"))
    if args.rebuild:
        for k in config.section_keys("bsdl"):
            val = config.path_get("bsdl", k)
            for f in glob.glob(val):
                cache.file_add(f)
        cache.save()

    if args.list:
        for entity in cache.filter():
            print("- %s/%s: %s" % (entity.name, entity.package_variant,
                                   [PartId.from_idcode(c.value).pretty() for c in entity.id_codes]))

    if args.id:
        idcode = int(args.id, 16)
        for entity in cache.filter(idcode = idcode):
            print("- %s/%s: %s" % (entity.name, entity.package_variant,
                                   [PartId.from_idcode(c.value).pretty() for c in entity.id_codes]))

if __name__ == "__main__":
    main()
