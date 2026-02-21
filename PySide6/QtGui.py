class QColor:
    def __init__(self, *args):
        self.value = args


class QPalette:
    Window = 1
    WindowText = 2
    Base = 3
    AlternateBase = 4
    ToolTipBase = 5
    ToolTipText = 6
    Text = 7
    Button = 8
    ButtonText = 9
    BrightText = 10
    Link = 11
    Highlight = 12
    HighlightedText = 13

    def __init__(self):
        self._colors = {}

    def setColor(self, role, color):
        self._colors[role] = color
