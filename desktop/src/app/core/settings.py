"""The settings that no rule decides: the voice, where the companion stands,
the one-time close notice, the add-ons, and the GPU of the model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.app.commands import (
    AddToolServer,
    CloseHintShown,
    CompanionMoved,
    DeviceChosen,
    RemoveToolServer,
    SetHotkey,
    SetSpeakAloud,
)
from src.domain.ports.tool_server_store import ToolServerStoreFailed
from src.domain.tools.models.tool_server import ToolServer
from src.infrastructure.storage.settings_store import SettingNotSaved

if TYPE_CHECKING:
    from src.app.core_host import CoreHost


class SettingsHandler:
    handles = (
        SetSpeakAloud,
        SetHotkey,
        CompanionMoved,
        CloseHintShown,
        AddToolServer,
        RemoveToolServer,
        DeviceChosen,
    )

    def __init__(self, core: CoreHost) -> None:
        self.core = core

    def start(self) -> None:
        settings, bridge = self.core.settings, self.core.bridge
        bridge.voiceSettingsShown.emit(settings.speak_aloud(), settings.talk_hotkey())
        bridge.placementShown.emit(settings.placement())
        bridge.closeHintShown.emit(settings.close_hint_shown())
        self._show_servers()

    def handle(self, item) -> None:
        settings, bridge = self.core.settings, self.core.bridge
        try:
            match item:
                case SetSpeakAloud(on):
                    settings.set_speak_aloud(on)
                    bridge.voiceSettingsShown.emit(on, settings.talk_hotkey())
                case SetHotkey(sequence):
                    settings.set_talk_hotkey(sequence)
                    bridge.voiceSettingsShown.emit(settings.speak_aloud(), sequence)
                case CompanionMoved(x, y, screen):
                    settings.set_placement(x, y, screen)
                case CloseHintShown():
                    settings.set_close_hint_shown()
                case AddToolServer() as draft:
                    self._add(draft)
                case RemoveToolServer(server_id):
                    self._remove(server_id)
                case DeviceChosen(name):
                    settings.set_chat_device(name)
        except SettingNotSaved as error:
            bridge.noticeShown.emit(str(error))
            bridge.voiceSettingsShown.emit(
                settings.speak_aloud(), settings.talk_hotkey()
            )

    def _add(self, draft: AddToolServer) -> None:
        now = self.core.clock()
        try:
            server = ToolServer(
                id=uuid.uuid4().hex,
                name=draft.name.strip(),
                transport=draft.transport,
                command=draft.command,
                args=draft.args,
                url=draft.url,
                added_at=now,
                consented_at=now,
            )
            self.core.tool_servers.add(server)
        except (ValueError, ToolServerStoreFailed) as error:
            self.core.bridge.toolServersFailed.emit(str(error))
            return
        self._show_servers()

    def _remove(self, server_id: str) -> None:
        try:
            self.core.tool_servers.remove(server_id)
        except ToolServerStoreFailed as error:
            self.core.bridge.toolServersFailed.emit(str(error))
            return
        self._show_servers()

    def _show_servers(self) -> None:
        try:
            servers = self.core.tool_servers.all()
        except ToolServerStoreFailed as error:
            self.core.bridge.toolServersFailed.emit(str(error))
            return
        self.core.bridge.toolServersShown.emit(servers)
        self.core.bridge.addOnsChanged.emit(servers)
