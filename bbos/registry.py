# registry.py
from functools import wraps
from inspect import isclass
from threading import Lock

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
def get_type(name: str):
    return _types[name]


def get_cfg(name: str):
    return _config[name]


def all_types():
    return _types.ctypey()


def all_cfg():
    return _config.ctypey()
