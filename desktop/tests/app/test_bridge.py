import threading

from PySide6.QtCore import QObject, QThread, Slot

from src.app.bridge import QUEUE_SIZE, Bridge
from src.app.commands import SendMessage


class Receiver(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, bool]] = []

    @Slot(str, str)
    def finished(self, text: str, note: str) -> None:
        on_gui = QThread.currentThread() is self.thread()
        self.calls.append((text, on_gui))


def test_send_puts_into_the_queue(qapp) -> None:
    bridge = Bridge()

    bridge.send(SendMessage("hi"))

    assert bridge.commands.get_nowait() == SendMessage("hi")
    assert bridge.commands.maxsize == QUEUE_SIZE


def test_signal_from_core_thread_arrives_on_gui_thread(qtbot) -> None:
    bridge = Bridge()
    receiver = Receiver()
    bridge.replyFinished.connect(receiver.finished)

    worker = threading.Thread(target=lambda: bridge.replyFinished.emit("Hello", ""))
    worker.start()
    worker.join()

    qtbot.waitUntil(lambda: bool(receiver.calls), timeout=2000)
    assert receiver.calls == [("Hello", True)]
