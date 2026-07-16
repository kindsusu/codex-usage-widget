from __future__ import annotations

from PIL import Image

from codex_usage_widget.pet_image import prepare_pet_image


def test_pet_image_removes_only_border_connected_near_white_background() -> None:
    source = Image.new("RGBA", (8, 8), (252, 251, 249, 255))
    for x in range(2, 6):
        for y in range(1, 7):
            source.putpixel((x, y), (36, 41, 47, 255))
    source.putpixel((3, 3), (255, 255, 255, 255))

    prepared = prepare_pet_image(source, 16)

    assert prepared.size == (16, 16)
    rgba = prepared.tobytes()
    assert rgba[3] == 0
    assert max(rgba[3::4]) == 255
    assert any(
        rgba[index : index + 4] == b"\xff\xff\xff\xff"
        for index in range(0, len(rgba), 4)
    )


def test_pet_image_crops_subject_before_nearest_neighbor_fit() -> None:
    source = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
    for x in range(48, 80):
        for y in range(24, 104):
            source.putpixel((x, y), (231, 132, 91, 255))

    prepared = prepare_pet_image(source, 16)
    alpha = prepared.getchannel("A")

    assert alpha.getbbox() == (5, 0, 11, 16)
    assert set(alpha.tobytes()) <= {0, 255}
