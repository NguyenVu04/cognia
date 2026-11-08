"""One running copy of Cognia. A second start asks the first to show its
window, then ends."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SHOW = b"show"


class SingleInstance(QObject):
    #: Another start asked this copy to show its window.
    activated = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None

    def claim(self) -> bool:
        """Become the running copy. False if another copy already runs."""
        if self.notify_running():
            return False
        QLocalServer.removeServer(self._key)
        server = QLocalServer(self)
        if not server.listen(self._key):
            return False
        server.newConnection.connect(self._connected)
        self._server = server
        return True

    def notify_running(self) -> bool:
        """Ask a running copy to show itself. False if none answers."""
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        if not socket.waitForConnected(300):
            return False
        socket.write(_SHOW)
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True

    def _connected(self) -> None:
        while self._server is not None and (
            socket := self._server.nextPendingConnection()
        ):
            socket.readyRead.connect(lambda s=socket: self._read(s))
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        if bytes(socket.readAll().data()).startswith(_SHOW):
            self.activated.emit()
        socket.disconnectFromServer()
