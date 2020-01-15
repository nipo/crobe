def find_pep420_plugins():
    """
    See https://packaging.python.org/guides/creating-and-discovering-plugins/
    """
    import importlib

    try:
        import crobe_plugin
    except:
        return
    
    def iter_namespace(ns_pkg):
        import pkgutil
        return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")

    discovered_plugins = {
        name: importlib.import_module(name)
        for finder, name, ispkg
        in iter_namespace(crobe_plugin)
    }

find_pep420_plugins()
