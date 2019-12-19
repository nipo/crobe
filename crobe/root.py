from .adapter.model import HwRoot

def roots(paths):
    try:
        HwRoot.start()
    except:
        pass

    r = []
    for root in paths:
        parts = root.split("/")
        r.append(HwRoot.child_summon(*parts))
    return r

def root(path):
    return roots([path])[0]
