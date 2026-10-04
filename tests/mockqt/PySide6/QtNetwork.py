from PySide6._any import make, Anything
_cache = {}
def __getattr__(name):
    if name.startswith("__"): raise AttributeError(name)
    if name not in _cache: _cache[name] = make(name)
    return _cache[name]
