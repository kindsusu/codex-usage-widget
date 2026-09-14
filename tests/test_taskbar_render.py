# pyright: reportAny=false, reportGeneralTypeIssues=false, reportIndexIssue=false, reportOptionalSubscript=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from PIL import Image

from codex_usage_widget.taskbar_model import TaskbarModel, TaskbarRow
from codex_usage_widget.taskbar_render import render_taskbar, taskbar_hit_regions


def _model(*, stale: bool = False) -> TaskbarModel:
    return TaskbarModel(
        rows=(
            TaskbarRow("5h", 72, "72%", "1시간 후 초기화"),
            TaskbarRow("주간", 38, "38%", "2일 후 초기화"),
        ),
        title="Codex Plus",
        status_text="최신",
        error_text=None,
        stale=stale,
    )


def test_full_renderer_is_transparent_outside_content_and_uses_exact_size() -> None:
    image = render_taskbar(_model(), dpi=96, width=197, height=46)

    assert image.mode == "RGBA"
    assert image.size == (197, 46)
    assert image.getpixel((0, 0))[3] == 0
    assert image.getpixel((196, 0))[3] == 0
    assert image.getbbox() is not None


def test_transparent_looking_button_interiors_remain_hit_testable() -> None:
    image = render_taskbar(_model(), dpi=96, width=197, height=46)

    assert image.getpixel((4, 23))[3] == 1  # menu button, now on the left
    assert image.getpixel((50, 23))[3] == 1  # usage button, now on the right
    assert image.getpixel((40, 23))[3] == 0  # five-pixel gap stays click-through


def test_hit_regions_match_approved_menu_gap_and_usage_width_at_each_dpi() -> None:
    assert taskbar_hit_regions(197, 46, 96).menu.left == 0
    assert taskbar_hit_regions(197, 46, 96).menu.right == 38
    assert taskbar_hit_regions(197, 46, 96).usage.left == 43
    assert taskbar_hit_regions(197, 46, 96).usage.right == 197

    scaled = taskbar_hit_regions(296, 69, 144)
    assert scaled.menu.left == 0
    assert scaled.menu.right == 57
    assert scaled.usage.left == 65
    assert scaled.usage.right == 296


def test_bar_is_short_and_colored_by_remaining_percent() -> None:
    # 2026-09-14: the bar was cut to 80% of its length (59px -> 47px) and the
    # severity colour carries the reading. 72% remaining is green, 38% amber.
    image = render_taskbar(_model(), dpi=96, width=185, height=46)
    bar_left = taskbar_hit_regions(185, 46, 96).usage.left + 45

    green = _color_extent(image, (24, 134, 75))
    amber = _color_extent(image, (194, 118, 18))
    track = _color_extent(image, (223, 230, 239))
    assert green is not None
    assert amber is not None
    assert track is not None
    assert green[0] >= bar_left
    assert amber[0] >= bar_left
    # the whole track, fill included, fits in 47px: the old bar ran 59px
    for extent in (green, amber, track):
        assert extent[1] <= bar_left + 47, extent


def _color_extent(
    image: Image.Image, rgb: tuple[int, int, int]
) -> tuple[int, int] | None:
    xs = [
        x
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y))[:3] == rgb and image.getpixel((x, y))[3] > 200
    ]
    return (min(xs), max(xs)) if xs else None


def test_light_and_dark_palettes_render_expected_track_and_fill_colors() -> None:
    light = render_taskbar(_model(), dpi=96, width=197, height=46)
    dark = render_taskbar(_model(), dpi=96, width=197, height=46, light_theme=False)

    assert _contains_rgb(light, (223, 230, 239))
    assert _contains_rgb(light, (24, 134, 75))
    assert _contains_rgb(light, (194, 118, 18))
    assert _contains_rgb(dark, (58, 69, 88))
    assert _contains_rgb(dark, (71, 199, 125))
    assert _contains_rgb(dark, (230, 168, 66))


def test_track_antialiasing_never_creates_brighter_rgb_fringe() -> None:
    image = render_taskbar(_model(), dpi=144, width=296, height=69)
    track = (223, 230, 239)

    for y in range(15, 26):
        for x in range(132, 224):
            pixel = image.getpixel((x, y))
            if not isinstance(pixel, tuple) or len(pixel) != 4:
                continue
            red, green, blue, alpha = pixel
            if alpha > 220 and red > 100:
                assert red <= track[0] + 2
                assert green <= track[1] + 2
                assert blue <= track[2] + 2


def test_hover_affects_only_requested_region() -> None:
    base = render_taskbar(_model(), dpi=96, width=197, height=46)
    usage = render_taskbar(
        _model(), dpi=96, width=197, height=46, hover_region="usage"
    )
    menu = render_taskbar(
        _model(), dpi=96, width=197, height=46, hover_region="menu"
    )

    assert usage.getpixel((50, 23))[3] > base.getpixel((50, 23))[3]
    assert usage.getpixel((4, 23)) == base.getpixel((4, 23))
    assert menu.getpixel((4, 23)) != base.getpixel((4, 23))
    assert menu.getpixel((50, 23)) == base.getpixel((50, 23))


def test_narrow_layout_omits_tracks_before_clipping_values() -> None:
    image = render_taskbar(_model(), dpi=96, width=120, height=46)

    assert image.size == (120, 46)
    assert not _contains_rgb(image, (223, 230, 239))
    assert image.getbbox() is not None


def test_stale_model_changes_menu_status_dot_from_green_to_amber() -> None:
    fresh = render_taskbar(_model(), dpi=96, width=197, height=46)
    stale = render_taskbar(_model(stale=True), dpi=96, width=197, height=46)

    assert _contains_rgb(fresh.crop((21, 28, 35, 43)), (24, 134, 75))
    assert _contains_rgb(stale.crop((21, 28, 35, 43)), (194, 118, 18))


def test_single_row_is_vertically_centered_and_long_error_is_condensed() -> None:
    single = TaskbarModel((_model().rows[0],), "Codex", "최신", None, False)
    error = TaskbarModel(
        (),
        "Codex",
        "사용 불가",
        "Codex 사용량을 불러올 수 없습니다.",
        False,
    )

    single_image = render_taskbar(single, dpi=96, width=197, height=46)
    error_image = render_taskbar(error, dpi=96, width=197, height=46)

    alpha = single_image.getchannel("A")
    assert alpha.crop((43, 14, 197, 32)).getbbox() is not None
    assert error_image.crop((38, 0, 43, 46)).getchannel("A").getextrema() == (0, 0)


def _contains_rgb(image: Image.Image, rgb: tuple[int, int, int]) -> bool:
    return any(
        all(abs(pixel[index] - rgb[index]) <= 3 for index in range(3))
        and pixel[3] >= 220
        for pixel in image.get_flattened_data()
    )
