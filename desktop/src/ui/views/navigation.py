"""The four destinations of the main window and their shortcuts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    icon: str
    shortcut: str


COMPANION = "companion"
MEMORY = "memory"
CHARACTER = "character"
SETTINGS = "settings"

NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(COMPANION, "Companion", "chat-circle", "Ctrl+1"),
    NavItem(MEMORY, "Memory", "brain", "Ctrl+2"),
    NavItem(CHARACTER, "Character", "user-focus", "Ctrl+3"),
    NavItem(SETTINGS, "Settings", "gear-six", "Ctrl+4"),
)
