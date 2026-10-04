class Anything:
    def __init__(self, *a, **k): pass
    def __getattr__(self, name):
        if "_" in name.strip("_") and not name.startswith("__"):
            raise AttributeError(f"{type(self).__name__}.{name}")
        if name.startswith("__"): raise AttributeError(name)
        fixed = {"count": 0, "value": 0, "maximum": 255, "minimum": 0, "currentRow": 0,
                 "currentIndex": 0, "text": "", "currentText": "80%", "findChildren": [],
                 "errorString": "err"}
        if name in fixed:
            v = fixed[name]
            return lambda *a, **k: v
        return Anything()
    def __call__(self, *a, **k): return Anything()
    def __iter__(self): return iter(())
    def __bool__(self): return True
    def __int__(self): return 0
    def __index__(self): return 0
    def __float__(self): return 0.0
    def __len__(self): return 0
    def __str__(self): return ""
    def __format__(self, spec): return ""
    def __hash__(self): return id(self)
    def __eq__(self, o): return self is o
    def __lt__(self, o): return False
    __gt__ = __le__ = __ge__ = __lt__
    def _op(self, *a): return Anything()
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __floordiv__ = __mod__ = _op
    __and__ = __rand__ = __or__ = __ror__ = __neg__ = _op
    def __class_getitem__(cls, k): return cls
class Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"): raise AttributeError(name)
        return Anything()
def make(name): return Meta(name, (Anything,), {})
