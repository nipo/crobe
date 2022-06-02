class Plugin:
    def __init__(self, name, module, path, loading_exc_info):
        self.name = name
        self.module = module
        self.path = path
        self.loading_exc_info = loading_exc_info

def _load_pep420_plugins():
    """
    See https://packaging.python.org/guides/creating-and-discovering-plugins/
    """
    import importlib
    import traceback
    import os
    import sys

    if os.getenv("CROBE_PLUGIN_DEBUG"):
        log = print
    else:
        def log(*args, **kwargs):
            pass

    log("Loading plugins...")

    try:
        import crobe_plugin
    except:
        log("namespace package not found")
        return
    
    def iter_namespace(ns_pkg):
        import pkgutil
        return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")

    plugins = []
    
    for finder, name, ispkg in iter_namespace(crobe_plugin):
        log(" - %s %s %s" % (finder, name, ispkg))
        try:
            m = importlib.import_module(name)
            exc_info = None
            log(" -> %s" % (m))
        except Exception as e:
            m = None
            exc_info = sys.exc_info()
            log(" ** %s" % (e))
            print("Plugin %s failed to load: %s" % (name, e))
        plugins.append(Plugin(name, m, finder.path, exc_info))
    return plugins

plugins = _load_pep420_plugins()
