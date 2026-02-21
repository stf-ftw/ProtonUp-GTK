from __future__ import annotations

class _SimpleSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback, *_args, **_kwargs):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class QMessageBox:
    Ok = 1
    Cancel = 2
    Warning = 3
    Information = 4

    class StandardButton:
        Ok = 1
        Cancel = 2

    class Icon:
        Information = 4
        Warning = 3

    def __init__(self):
        self.checkbox = None

    def setWindowTitle(self, *_args, **_kwargs):
        pass

    def setText(self, *_args, **_kwargs):
        pass

    def setInformativeText(self, *_args, **_kwargs):
        pass

    def setStandardButtons(self, *_args, **_kwargs):
        pass

    def setDefaultButton(self, *_args, **_kwargs):
        pass

    def setDetailedText(self, *_args, **_kwargs):
        pass

    def setIcon(self, *_args, **_kwargs):
        pass

    def addButton(self, *_args, **_kwargs):
        return object()

    def setCheckBox(self, cb):
        self.checkbox = cb

    def exec(self):
        return self.Ok

    @staticmethod
    def aboutQt(_parent=None):
        pass


class QCheckBox:
    def __init__(self, *_args, **_kwargs):
        self._checked = False

    def isChecked(self):
        return self._checked


class QComboBox:
    def __init__(self):
        self._items = []

    def count(self):
        return len(self._items)

    def itemText(self, i):
        return self._items[i]


class _Style:
    def standardPalette(self):
        return None


class QStyleFactory:
    @staticmethod
    def create(_name):
        return _Style()


class QApplication:
    _instance = None

    def __init__(self):
        self.message_box_message = _SimpleSignal()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
