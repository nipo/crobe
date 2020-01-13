from .adapter.model import HwRoot

def roots(paths):
    HwRoot.start_root()

    r = []
    for root in paths:
        parts = root.split("/")
        r.append(HwRoot.child_summon(*parts))
    return r

def root(path):
    return roots([path])[0]
