# registry.py
from typing import List
from inspect import isclass
from threading import Lock
import numpy as np

_periods: dict[str, float] = {}
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

def realtime(ms: int):
    """Decorator that registers a type that updates at a given period in milliseconds."""
    def deco(obj):
        key = obj.__name__
        assert not isclass(obj), "period decorator must be used on a type function"

        with _lock:
            if key in _types:
                raise ValueError(
                    f"‘{key}’ already registered in {_types is _config and 'config' or 'types'}"
                )
            _types[key] = obj
            _periods[key] = ms
        return obj  # object remains intact
    return deco

# --- helpers ---------------------------------------------------------------
class Type:
    def __init__(self, name: str):
        self._name = name

    def __call__(self, *args, **kwargs):
        return _types[self._name](*args, **kwargs)+[("timestamp", 'datetime64[ns]')], _periods[self._name]


class Config:

    def __init__(self, name: str):
        cfg = _config[name]
        for k, v in cfg.__dict__.items():
            if not (k.startswith('__') and k.endswith('__')):
                setattr(self, k, v)
        self._name = name


def all_types():
    return {k: v() + [("timestamp", 'datetime64[ns]')] for k, v in _types.items()}


def all_cfg():
    return _config
