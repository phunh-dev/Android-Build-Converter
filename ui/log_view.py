"""Scrollable, colorized log pane for streaming bundletool output."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

_COLOR_STDOUT = "#d4d4dc"
_COLOR_STDERR = "#ff8080"
_COLOR_SUCCESS = "#5fd97f"
_COLOR_WARNING = "#e6c15c"
_COLOR_SYSTEM = "#8a8ad0"


class LogView(QPlainTextEdit):
    """Read-only, monospace, auto-scrolling log output. Auto-scroll pauses
    while the user has scrolled up to read earlier output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(20000)  # cap memory on very long/verbose builds
        font = self.font()
        font.setFamily("Consolas" if self._is_windows() else "Menlo")
        font.setStyleHint(font.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet(
            "QPlainTextEdit { background-color: #1c1c22; color: #d4d4dc; "
            "border: 1px solid #3a3a44; border-radius: 6px; padding: 6px; }"
        )

    @staticmethod
    def _is_windows() -> bool:
        import platform

        return platform.system() == "Windows"

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def append_line(self, text: str, *, is_stderr: bool = False) -> None:
        color = _COLOR_STDERR if is_stderr else _COLOR_STDOUT
        self._append_colored(text, color)

    def append_success(self, text: str) -> None:
        self._append_colored(text, _COLOR_SUCCESS)

    def append_warning(self, text: str) -> None:
        self._append_colored(text, _COLOR_WARNING)

    def append_system(self, text: str) -> None:
        self._append_colored(text, _COLOR_SYSTEM)

    def _append_colored(self, text: str, color: str) -> None:
        was_at_bottom = self._at_bottom()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        if was_at_bottom:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())
