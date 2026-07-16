"""Background-safe pixel-art preparation for pet assets."""

from __future__ import annotations

from collections import deque
from typing import Final

from PIL import Image

_BACKGROUND_DISTANCE: Final = 22
_RGBA_CHANNELS: Final = 4


def prepare_pet_image(source: Image.Image, target_size: int) -> Image.Image:
    """Remove edge-connected background, crop, and fit with crisp pixels."""
    image = source.convert("RGBA")
    width, height = image.size
    data = bytearray(image.tobytes())
    background = _corner_background(data, width, height)
    queue = deque(_edge_points(width, height))
    visited: set[tuple[int, int]] = set()
    while queue:
        point = queue.popleft()
        if point in visited:
            continue
        visited.add(point)
        x, y = point
        offset = (y * width + x) * 4
        pixel = tuple(data[offset : offset + 4])
        if not _matches_background(pixel, background):
            continue
        data[offset + 3] = 0
        queue.extend(_neighbors(x, y, width, height))
    transparent = Image.frombytes("RGBA", (width, height), bytes(data))
    bounds = transparent.getbbox()
    if bounds is None:
        return Image.new("RGBA", (target_size, target_size))
    subject = transparent.crop(bounds)
    subject.thumbnail((target_size, target_size), Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", (target_size, target_size))
    x = (target_size - subject.width) // 2
    y = (target_size - subject.height) // 2
    canvas.alpha_composite(subject, (x, y))
    return canvas


def _corner_background(
    data: bytearray,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    corner_offsets = (
        0,
        (width - 1) * 4,
        (height - 1) * width * 4,
        (width * height - 1) * 4,
    )
    return (
        round(sum(data[offset + 0] for offset in corner_offsets) / 4),
        round(sum(data[offset + 1] for offset in corner_offsets) / 4),
        round(sum(data[offset + 2] for offset in corner_offsets) / 4),
        round(sum(data[offset + 3] for offset in corner_offsets) / 4),
    )


def _matches_background(
    pixel: tuple[int, ...],
    background: tuple[int, int, int, int],
) -> bool:
    if len(pixel) != _RGBA_CHANNELS or pixel[3] == 0:
        return True
    distance = max(abs(pixel[index] - background[index]) for index in range(3))
    return distance <= _BACKGROUND_DISTANCE


def _edge_points(width: int, height: int) -> tuple[tuple[int, int], ...]:
    horizontal = tuple((x, y) for x in range(width) for y in (0, height - 1))
    vertical = tuple((x, y) for y in range(height) for x in (0, width - 1))
    return horizontal + vertical


def _neighbors(
    x: int,
    y: int,
    width: int,
    height: int,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (next_x, next_y)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        if 0 <= next_x < width and 0 <= next_y < height
    )
