import ctypes as _c
import os
import os.path
import sys
import glob

__all__ = ["load"]

def try_load(paths, name, *vers):
    name_formats = ["lib%(name)s.%(ver)d.dylib",
                    "lib%(name)s.so.%(ver)d",
                    "lib%(name)s.dll"]

    for path in paths:
        for ver in vers:
            for f in name_formats:
                filename = os.path.join(path, f % dict(name = name, ver = ver))
                if not os.path.exists(filename):
                    continue
                try:
                    if sys.platform == 'darwin':
                        return _c.CDLL(filename, _c.RTLD_GLOBAL)
                    else:
                        return _c.cdll.LoadLibrary(filename)
                except OSError as e:
                    pass

def try_load_env_path(var, name, *vers):
    return try_load([_f for _f in os.environ.get(var, "").split(":") if _f], name, *vers)

def ld_so_conf_paths(filename):
    try:
        fd = open(filename, "rb")
    except Exception as e:
        return []

    ret = []
    
    for l in fd.readlines():
        l = l.strip()
        if l.startswith(b"#") or not l:
            continue
        if l.startswith(b"/"):
            ret.append(str(l, 'utf-8'))
        if l.startswith(b"include "):
            for f in glob.glob(l[8:]):
                ret += ld_so_conf_paths(f)
    return ret

def load(name, *vers):

    libpath = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"

    default_paths = []
    if sys.platform.startswith("linux"):
        default_paths += ld_so_conf_paths("/etc/ld.so.conf")
    default_paths += [os.path.expanduser('~/lib'),
                      os.path.expanduser('~/local/lib'),
                      '/usr/local/lib',
                      '/usr/lib']

    lib = try_load_env_path(libpath, name, *vers) \
           or try_load(default_paths, name, *vers)

    if not lib:
        raise RuntimeError("Unable to load library '%s'", name)

    return lib

