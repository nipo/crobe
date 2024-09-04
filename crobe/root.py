from .adapter.model import HwRoot
import re

def roots(paths):
    HwRoot.start_root()

    splitter = re.compile(r'([a-z0-9._:@-]+(\([^\)]*\))?)', re.I)

    r = []
    for root in paths:
        parts = splitter.split(root)
        if not all((p in ["", "/"]) for p in parts[0::3]):
            raise ValueError(root)
        parts = parts[1::3]
        r.append(HwRoot.child_summon(*parts))
    return r

def root(path):
    return roots([path])[0]
