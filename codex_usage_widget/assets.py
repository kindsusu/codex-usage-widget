"""Deterministic manifest and safe loading for widget PNG assets."""

from __future__ import annotations

import hashlib
import io
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from PIL import Image


@dataclass(frozen=True, slots=True)
class PetAsset:
    """Stable original pet name and its filesystem-safe filename."""

    name: str
    filename: str


PET_ASSETS: Final = tuple(
    PetAsset(name, filename)
    for name, filename in (
        ("image (1)", "image-1.png"),
        ("image (10)", "image-10.png"),
        ("image (11)", "image-11.png"),
        ("image (12)", "image-12.png"),
        ("image (13)", "image-13.png"),
        ("image (14)", "image-14.png"),
        ("image (15)", "image-15.png"),
        ("image (16)", "image-16.png"),
        ("image (17)", "image-17.png"),
        ("image (18)", "image-18.png"),
        ("image (19)", "image-19.png"),
        ("image (2)", "image-2.png"),
        ("image (20)", "image-20.png"),
        ("image (3)", "image-3.png"),
        ("image (4)", "image-4.png"),
        ("image (5)", "image-5.png"),
        ("image (6)", "image-6.png"),
        ("image (7)", "image-7.png"),
        ("image (8)", "image-8.png"),
        ("image (9)", "image-9.png"),
        ("image_add_renew(1)", "image-add-renew-1.png"),
        ("image_add_renew(10)", "image-add-renew-10.png"),
        ("image_add_renew(2)", "image-add-renew-2.png"),
        ("image_add_renew(3)", "image-add-renew-3.png"),
        ("image_add_renew(4)", "image-add-renew-4.png"),
        ("image_add_renew(5)", "image-add-renew-5.png"),
        ("image_add_renew(6)", "image-add-renew-6.png"),
        ("image_add_renew(7)", "image-add-renew-7.png"),
        ("image_add_renew(8)", "image-add-renew-8.png"),
        ("image_add_renew(9)", "image-add-renew-9.png"),
    )
)
PET_NAMES: Final = tuple(asset.name for asset in PET_ASSETS)
ASSET_ROOT: Final = Path(__file__).resolve().parent.parent / "assets"
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
MINI_ICON_ASSETS: Final[frozenset[str]] = frozenset(
    {"codex-color.png", "codex-color-dark.png"}
)
_MINI_ICON_TILE_COLORS: Final[dict[str, tuple[int, int, int]]] = {
    "codex-color.png": (255, 255, 255),
    "codex-color-dark.png": (30, 30, 46),
}
_TILE_COLOR_TOLERANCE: Final = 12


def load_pet_png(name: str, *, root: Path = ASSET_ROOT) -> bytes:
    """Read a named pet PNG, returning a generated 16px fallback on failure."""
    filename = next(
        (asset.filename for asset in PET_ASSETS if asset.name == name),
        None,
    )
    if filename is None:
        return _fallback_png(16, 16)
    return _read_png(root / "pets" / filename, (128, 128), (16, 16))


def load_tray_png(*, root: Path = ASSET_ROOT) -> bytes:
    """Read the tray icon, returning a generated fallback on failure."""
    return _read_png(root / "icon" / "codex.png", (64, 64), (32, 32))


def load_mini_icon_png(name: str, *, root: Path = ASSET_ROOT) -> bytes:
    """Read one theme-specific Codex mini icon with a safe fallback."""
    if name not in MINI_ICON_ASSETS:
        return _fallback_png(24, 24)
    raw = _read_png(root / "icon" / name, (64, 64), (24, 24))
    return _clear_solid_tile(raw, _MINI_ICON_TILE_COLORS[name])


def asset_manifest_digest(*, root: Path = ASSET_ROOT) -> str:
    """Hash ordered names, filenames, and bytes to prove asset provenance."""
    digest = hashlib.sha256()
    for asset in PET_ASSETS:
        digest.update(asset.name.encode())
        digest.update(b"\0")
        digest.update(asset.filename.encode())
        digest.update(b"\0")
        digest.update(load_pet_png(asset.name, root=root))
    return digest.hexdigest()


def _read_png(
    path: Path,
    expected_size: tuple[int, int],
    fallback_size: tuple[int, int],
) -> bytes:
    try:
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw), formats=("PNG",)) as image:
            if image.format != "PNG" or image.size != expected_size:
                return _fallback_png(*fallback_size)
            image.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        return _fallback_png(*fallback_size)
    return raw


def _clear_solid_tile(raw: bytes, tile: tuple[int, int, int]) -> bytes:
    with Image.open(io.BytesIO(raw), formats=("PNG",)) as source:
        image = source.convert("RGBA")
    pixels = image.load()
    if pixels is None:
        return raw
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = cast(
                "tuple[int, int, int, int]",
                image.getpixel((x, y)),
            )
            if (
                max(
                    abs(red - tile[0]),
                    abs(green - tile[1]),
                    abs(blue - tile[2]),
                )
                <= _TILE_COLOR_TOLERANCE
            ):
                pixels[x, y] = (red, green, blue, 0)
            elif alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fallback_png(width: int, height: int) -> bytes:
    pixel = b"\x25\x63\xeb\xff"
    scanlines = b"".join(b"\0" + pixel * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(
            b"IDAT",
            zlib.compress(scanlines),
        )
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
