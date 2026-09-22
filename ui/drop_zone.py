"""A reusable drag-and-drop-or-click file picker widget.

Qt's drag & drop is a first-class framework feature (dragEnterEvent /
dropEvent), unlike Tkinter where it requires a separate compiled extension
(tkinterdnd2) with known PyInstaller packaging issues. No extra dependency
needed here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout, QWidget


class DropZone(QFrame):
    """Click-or-drag file picker. Emits file_selected(str) with the chosen
    absolute path once a file matching `extensions` is provided."""

    file_selected = Signal(str)

    _STYLE_IDLE = """
        DropZone {
            border: 2px dashed #4a4a55;
            border-radius: 10px;
            background-color: #2b2b33;
        }
        DropZone:hover {
            border-color: #6a6a78;
        }
    """
    _STYLE_ACTIVE = """
        DropZone {
            border: 2px dashed #4f9dff;
            border-radius: 10px;
            background-color: #24324a;
        }
    """
    _STYLE_REJECTED = """
        DropZone {
            border: 2px dashed #ff5f5f;
            border-radius: 10px;
            background-color: #3a2323;
        }
    """
    _STYLE_FILLED = """
        DropZone {
            border: 2px solid #3fbf6f;
            border-radius: 10px;
            background-color: #223328;
        }
    """

    def __init__(
        self,
        extensions: tuple[str, ...],
        placeholder_text: str,
        file_dialog_filter: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._extensions = tuple(e.lower() for e in extensions)
        self._file_dialog_filter = file_dialog_filter
        self._selected_path: str | None = None

        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._STYLE_IDLE)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(placeholder_text)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._placeholder_text = placeholder_text

    @property
    def selected_path(self) -> str | None:
        return self._selected_path

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder_text = text
        if self._selected_path is None:
            self._label.setText(text)

    def clear(self) -> None:
        self._selected_path = None
        self._label.setText(self._placeholder_text)
        self.setStyleSheet(self._STYLE_IDLE)

    def _matches_extension(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._extensions

    def _accept_path(self, path: str) -> None:
        self._selected_path = path
        self._label.setText(Path(path).name)
        self.setStyleSheet(self._STYLE_FILLED)
        self.file_selected.emit(path)

    # --- drag & drop ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        urls = event.mimeData().urls()
        if len(urls) == 1 and self._matches_extension(urls[0].toLocalFile()):
            self.setStyleSheet(self._STYLE_ACTIVE)
            event.acceptProposedAction()
        else:
            self.setStyleSheet(self._STYLE_REJECTED)
            event.acceptProposedAction()  # accept so dragLeaveEvent fires and resets style

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        self.setStyleSheet(self._STYLE_FILLED if self._selected_path else self._STYLE_IDLE)

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1:
            path = urls[0].toLocalFile()
            if self._matches_extension(path):
                self._accept_path(path)
                event.acceptProposedAction()
                return
        self.setStyleSheet(self._STYLE_FILLED if self._selected_path else self._STYLE_IDLE)
        event.ignore()

    # --- click to browse ---

    def mousePressEvent(self, event) -> None:  # noqa: ANN001 - Qt event type
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse()
        super().mousePressEvent(event)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, filter=self._file_dialog_filter)
        if path:
            self._accept_path(path)
