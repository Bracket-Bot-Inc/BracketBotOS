# registry.py
from functools import wraps
from inspect import isclass
from threading import Lock
import numpy as np

_types: dict[str, callable] = {}  # functions & callables
_config: dict[str, type] = {}  # classes
_lock = Lock()


def register(robj):
    """Decorator that drtypes functions into _types and classes into _config."""

    def deco(obj):
        key = obj.__name__
        store = _config if isclass(obj) else _types  # branch once

        with _lock:
            if key in store:
                raise ValueError(
                    f"‘{key}’ already registered in {store is _config and 'config' or 'types'}"
                )
            store[key] = obj
        return obj  # object remains intact

    return deco(robj)


# --- helpers ---------------------------------------------------------------
class Type:
    def __init__(self, name: str):
        self._name = name

    def __call__(self, *args, **kwargs):
        return _types[self._name](*args, **kwargs) + [("timestamp", np.float64)
                                                      ]


class Config:

    def __init__(self, name: str):
        cfg = _config[name]
        for k, v in cfg.__dict__.items():
            if not (k.startswith('__') and k.endswith('__')):
                setattr(self, k, v)
        self._name = name


def all_types():
    import numpy as np
    return {k: v() + [("timestamp", np.float64)] for k, v in _types.items()}


def all_cfg():
    return _config
