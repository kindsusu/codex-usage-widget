import io
import re
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from codex_usage_widget.assets import (
    PET_ASSETS,
    asset_manifest_digest,
    load_pet_png,
    load_tray_png,
)


EXPECTED_MANIFEST_SHA256 = (
    "d8c00f1ee4953daca8073c9885e584395f1248e0bf691f796eea6d3f2ee57b89"
)


def _huge_png_header() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 100_000, 100_000, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")


def test_pet_manifest_preserves_all_named_assets_in_deterministic_order() -> None:
    # Given / When
    names = tuple(asset.name for asset in PET_ASSETS)
    filenames = tuple(asset.filename for asset in PET_ASSETS)

    # Then
    assert len(names) == 31
    assert names == tuple(sorted(names))
    assert len(set(names)) == 31
    assert len(set(filenames)) == 31
    assert all(re.fullmatch(r"[a-z0-9-]+\.png", name) for name in filenames)


def test_extracted_pet_pngs_match_reference_integrity_and_dimensions() -> None:
    # Given / When
    dimensions: list[tuple[int, int]] = []
    for asset in PET_ASSETS:
        raw = load_pet_png(asset.name)
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        with Image.open(io.BytesIO(raw)) as image:
            dimensions.append((image.width, image.height))

    # Then
    assert set(dimensions) == {(128, 128)}
    assert asset_manifest_digest() == EXPECTED_MANIFEST_SHA256


def test_tray_png_uses_a_square_transparent_codex_icon() -> None:
    # Given / When
    raw = load_tray_png()

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (64, 64)
        assert image.getchannel("A").getbbox() is not None


def test_missing_pet_asset_returns_generated_valid_png(tmp_path: Path) -> None:
    # Given
    empty_asset_root = tmp_path

    # When
    raw = load_pet_png("image (1)", root=empty_asset_root)

    # Then
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (16, 16)


@pytest.mark.parametrize(
    "corrupt_bytes",
    [b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x01"],
)
def test_corrupt_pet_asset_returns_generated_fallback(
    tmp_path: Path,
    corrupt_bytes: bytes,
) -> None:
    # Given
    pet = PET_ASSETS[0]
    path = tmp_path / "pets" / pet.filename
    path.parent.mkdir()
    _ = path.write_bytes(corrupt_bytes)

    # When
    raw = load_pet_png(pet.name, root=tmp_path)

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (16, 16)
        image.verify()


def test_wrong_sized_pet_asset_returns_generated_fallback(tmp_path: Path) -> None:
    # Given
    pet = PET_ASSETS[0]
    path = tmp_path / "pets" / pet.filename
    path.parent.mkdir()
    Image.new("RGBA", (64, 64), "red").save(path, format="PNG")

    # When
    raw = load_pet_png(pet.name, root=tmp_path)

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (16, 16)


def test_corrupt_or_wrong_sized_tray_asset_returns_generated_fallback(
    tmp_path: Path,
) -> None:
    # Given
    path = tmp_path / "icon" / "codex.png"
    path.parent.mkdir()
    Image.new("RGBA", (1, 1), "red").save(path, format="PNG")

    # When
    raw = load_tray_png(root=tmp_path)

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (32, 32)


def test_decompression_bomb_pet_asset_returns_generated_fallback(
    tmp_path: Path,
) -> None:
    # Given
    pet = PET_ASSETS[0]
    path = tmp_path / "pets" / pet.filename
    path.parent.mkdir()
    _ = path.write_bytes(_huge_png_header())

    # When
    raw = load_pet_png(pet.name, root=tmp_path)

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (16, 16)


def test_decompression_bomb_tray_asset_returns_generated_fallback(
    tmp_path: Path,
) -> None:
    # Given
    path = tmp_path / "icon" / "codex.png"
    path.parent.mkdir()
    _ = path.write_bytes(_huge_png_header())

    # When
    raw = load_tray_png(root=tmp_path)

    # Then
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (32, 32)
