"""A character's picture, read from the thumbnail inside its VRM file.

A VRM file is a binary glTF: a JSON chunk that names the thumbnail image, and a
binary chunk that holds its bytes. Reading only those two chunks needs no 3D
renderer, so the pickers can show the characters cheaply.
"""

from __future__ import annotations

import json
import struct
from functools import cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap

from src.utils.paths import resource

_MAGIC = b"glTF"
_JSON = 0x4E4F534A
_BIN = 0x004E4942


def vrm_path(appearance_id: str) -> Path:
    return resource("companion", appearance_id, f"{appearance_id}.vrm")


def thumbnail_bytes(path: Path) -> bytes | None:
    """The encoded thumbnail of the VRM at ``path``, or ``None`` if the file is
    missing, is not a binary glTF, or names no thumbnail."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 20 or data[:4] != _MAGIC:
        return None
    chunks: dict[int, bytes] = {}
    offset = 12
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunks[kind] = data[offset + 8 : offset + 8 + length]
        offset += 8 + length
    if _JSON not in chunks or _BIN not in chunks:
        return None
    try:
        document = json.loads(chunks[_JSON])
        image = document["images"][_thumbnail_index(document)]
        view = document["bufferViews"][image["bufferView"]]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    start = view.get("byteOffset", 0)
    return chunks[_BIN][start : start + view["byteLength"]]


def _thumbnail_index(document: dict) -> int:
    extensions = document.get("extensions", {})
    if "VRMC_vrm" in extensions:
        return extensions["VRMC_vrm"]["meta"]["thumbnailImage"]
    texture = extensions["VRM"]["meta"]["texture"]
    return document["textures"][texture]["source"]


@cache
def _image(appearance_id: str) -> QImage | None:
    encoded = thumbnail_bytes(vrm_path(appearance_id))
    if encoded is None:
        return None
    image = QImage.fromData(encoded)
    return None if image.isNull() else image


def portrait(appearance_id: str, size: QSize) -> QPixmap | None:
    """The thumbnail cropped to fill ``size``, or ``None`` if there is none."""
    image = _image(appearance_id)
    if image is None:
        return None
    scaled = image.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = (scaled.width() - size.width()) // 2
    y = (scaled.height() - size.height()) // 2
    return QPixmap.fromImage(scaled.copy(x, y, size.width(), size.height()))
