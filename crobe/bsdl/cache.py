try:
    from vhsic.bsdl import bsdl
except ModuleNotFoundError:
    bsdl = None

from ..part_id import PartId
import json
import os
import sys
import os.path
import logging
import glob
try:
    from hashlib import blake2b
except:
    from hashlib import md5 as blake2b

class Cache:
    def __init__(self, path):
        self.logger = logging.getLogger("BSDL")
        self.path = path
        self.by_idcode_package = {}
        self.by_name_package = {}
        try:
            self.load()
        except Exception:
            self.create()
        self.check()

    def cache_filename(self, filename):
        h = blake2b(digest_size=20)
        h.update(filename.encode("utf-8"))
        return os.path.join(self.path, h.hexdigest() + ".json.gz")

    def clear(self):
        self.by_idcode_package = {}
        self.by_name_package = {}

    def create(self):
        os.makedirs(self.path, exist_ok = True)
        self.save()

    def check(self):
        for k in list(self.by_idcode_package.keys()):
            cache_filename = self.by_idcode_package[k]
            if not os.path.exists(cache_filename):
                del self.by_idcode_package[k]
        for k in list(self.by_name_package.keys()):
            cache_filename = self.by_name_package[k]
            if not os.path.exists(cache_filename):
                del self.by_name_package[k]
        
    def rebuild(self):
        self.clear()
        self.add(self.path)

    def directory_add(self, dirname):
        for root, dirs, files in os.walk(dirname):
            for f in files:
                filename = os.path.join(root, f)
                self.file_add(self, filename)

    def file_add(self, filename):
        if not bsdl:
            self.logger.error("vhsic.bsdl not loaded, ignoring")
            return
        self.logger.trace("Parsing %s...", filename)
        cache_filename = self.cache_filename(filename)
        entity = None

        if os.path.exists(cache_filename) \
           and os.path.getmtime(cache_filename) > os.path.getmtime(filename):
            try:
                entity = bsdl.Entity.load(cache_filename)
                self.logger.trace("Loaded from preparsed file")
            except Exception:
                pass

        if not entity:
            try:
                entity = bsdl.Entity.load(filename)
            except Exception:
                self.logger.error("Parsing failure in %s", filename, exc_info = sys.exc_info())
                return

            entity.dump(cache_filename)

        #if not entity.id_codes:
        #    print("no ID Codes")
        #    return

        self.logger.note("Found %s/%s: %s", entity.name, entity.package_variant,
                         [PartId.from_idcode(c.value).pretty() for c in entity.id_codes])

        for code in entity.id_codes:
            self.by_idcode_package[(code, entity.package_variant)] = cache_filename
        self.by_name_package[(entity.name, entity.package_variant)] = cache_filename

    def filter(self, name = None, idcode = None, package = None):
        if not bsdl:
            self.logger.error("vhsic.bsdl not loaded, nothing returned")
            return []
        r = set()
        if idcode is not None:
            for (code, pv), filename in self.by_idcode_package.items():
                if code.mask & idcode != code.value:
                    continue
                if package and pv != package:
                    continue
                e = bsdl.Entity.load(os.path.join(self.path, filename))
                r.add(e)

        if name is not None:
            for (pname, pv), filename in self.by_name_package.items():
                if pname != name:
                    continue
                if package and pv != package:
                    continue
                e = bsdl.Entity.load(os.path.join(self.path, filename))
                r.add(e)
        if idcode is None and name is None:
            for (pname, pv), filename in self.by_name_package.items():
                e = bsdl.Entity.load(os.path.join(self.path, filename))
                r.add(e)
        return list(sorted(r)) # , key = lambda x:(x.name, x.id_codes)))

    def load(self):
        if not bsdl:
            self.logger.error("vhsic.bsdl not loaded, nothing done")
            return

        cache = os.path.join(self.path, "index.json")
        obj = json.load(open(cache, "r"))
        for k, v in obj["by_idcode_package"].items():
            try:
                idc, package = k.split("/", 1)
            except:
                continue
            self.by_idcode_package[(bsdl.Pattern(idc), package)] = v
        for k, v in obj["by_name_package"].items():
            try:
                name, package = k.split("/", 1)
            except:
                continue
            self.by_name_package[(name, package)] = v

    def save(self):
        cache = os.path.join(self.path, "index.json")
        by_idcode_package = {}
        for (idcode, package), v in self.by_idcode_package.items():
            by_idcode_package[str(idcode)+"/"+package] = v
        by_name_package = {}
        for (name, package), v in self.by_name_package.items():
            by_name_package[name+"/"+package] = v

        obj = {"by_idcode_package": by_idcode_package,
               "by_name_package": by_name_package}

        fd = open(cache, "w")
        json.dump(obj, fd)
        fd.close()

    @classmethod
    def open(cls):
        from .. import config
        return cls(config.path_get("cache", "bsdl"))

    def rebuild(self):
        from .. import config
        for k in config.section_keys("bsdl"):
            val = config.path_get("bsdl", k)
            for f in glob.glob(val):
                self.file_add(f)
        self.save()
