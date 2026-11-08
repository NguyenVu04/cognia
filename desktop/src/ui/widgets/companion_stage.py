"""The web view that draws the 3D companion.

The page and the character load from local files only: a request interceptor
refuses every other URL, and the profile is off the record, so Chromium keeps
no cache or cookies on disk. The page answers through a web channel object:
``ready`` once the character stands, ``failed`` with a reason otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, QUrlQuery, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

from src.utils.paths import resource


def allowed(url: QUrl, root: Path) -> bool:
    """Whether the page may load ``url``: a file under ``root`` or a Qt resource."""
    if url.scheme() == "qrc":
        return True
    if not url.isLocalFile():
        return False
    try:
        Path(url.toLocalFile()).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


class LocalOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    """Blocks every request that :func:`allowed` refuses."""

    def __init__(self, root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = root

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        if not allowed(info.requestUrl(), self._root):
            info.block(True)


class _Host(QObject):
    """The object the page calls back."""

    ready = Signal()
    failed = Signal(str)

    @Slot()
    def pageReady(self) -> None:
        self.ready.emit()

    @Slot(str)
    def pageFailed(self, reason: str) -> None:
        self.failed.emit(reason)


def call_script(function: str, *args) -> str:
    """The JavaScript that calls ``cognia.<function>`` with ``args``, each
    written as JSON so that no argument can break out of the call."""
    arguments = ", ".join(json.dumps(a) for a in args)
    return f"window.cognia && window.cognia.{function}({arguments});"


class CompanionStage(QWebEngineView):
    """Draws one VRM character. Calls made before the page is ready wait."""

    ready = Signal()
    failed = Signal(str)

    def __init__(self, appearance_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = resource("companion")
        self._profile = QWebEngineProfile(self)
        self._interceptor = LocalOnlyInterceptor(root, self)
        self._profile.setUrlRequestInterceptor(self._interceptor)
        page = QWebEnginePage(self._profile, self)
        settings = page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        self._host = _Host(self)
        self._host.ready.connect(self._on_ready)
        self._host.failed.connect(self.failed)
        channel = QWebChannel(page)
        channel.registerObject("host", self._host)
        page.setWebChannel(channel)
        self.setPage(page)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ready = False
        self._waiting: list[str] = []

        url = QUrl.fromLocalFile(str(root / "page" / "index.html"))
        query = QUrlQuery()
        vrm = QUrl.fromLocalFile(str(root / appearance_id / f"{appearance_id}.vrm"))
        query.addQueryItem(
            "vrm", vrm.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        )
        url.setQuery(query)
        self.load(url)

    def call(self, function: str, *args) -> None:
        script = call_script(function, *args)
        if self._ready:
            self.page().runJavaScript(script)
        else:
            self._waiting.append(script)

    def isReady(self) -> bool:
        return self._ready

    def _on_ready(self) -> None:
        self._ready = True
        for script in self._waiting:
            self.page().runJavaScript(script)
        self._waiting.clear()
        self.ready.emit()
