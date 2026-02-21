from __future__ import annotations

from weakref import WeakKeyDictionary


class _BoundSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback, *_args, **_kwargs):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class Signal:
    def __init__(self, *_args, **_kwargs):
        self._store = WeakKeyDictionary()

    def __get__(self, obj, _owner):
        if obj is None:
            return self
        if obj not in self._store:
            self._store[obj] = _BoundSignal()
        return self._store[obj]


def Slot(*_args, **_kwargs):
    def _decorator(func):
        return func

    return _decorator


def Property(_type, fget=None, fset=None):
    return property(fget, fset)


class QObject:
    def tr(self, text: str):
        return text


class Qt:
    white = '#ffffff'
    black = '#000000'
    red = '#ff0000'


class _CoreApp(QObject):
    def translate(self, _context: str, text: str):
        return text


class QCoreApplication:
    _instance = _CoreApp()

    @classmethod
    def instance(cls):
        return cls._instance
