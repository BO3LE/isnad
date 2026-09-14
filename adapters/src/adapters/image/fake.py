from __future__ import annotations

import struct
import zlib
from typing import Literal


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class FakeImage:
    """A solid ink-coloured PNG. The real image provider is still to be chosen (risk R1)."""

    async def generate(self, prompt: str, *, aspect: Literal["landscape", "square"]) -> bytes:
        size = (320, 180) if aspect == "landscape" else (240, 240)
        return _png(*size, rgb=(11, 11, 10))
