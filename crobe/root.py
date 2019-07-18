from .adapter.model import Enumerator

def roots(paths):
    try:
        Enumerator.singleton.start()
    except:
        pass

    r = []
    for root in paths:
        parts = root.split("/")
        r.append(Enumerator.singleton.child_summon(*parts))
    return r

def root(path):
    return roots([path])[0]
