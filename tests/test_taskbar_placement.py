from codex_usage_widget.taskbar_placement import (
    PlacementFailure,
    Rect,
    TaskbarGeometry,
    place_taskbar_widget,
)


def test_prefers_the_free_run_at_the_leading_edge_margin() -> None:
    # 2026-09-15: the flat 200px Widgets reserve is gone; the sweep starts at
    # an 8px edge margin and only real obstacles push it right.
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(500, 1000, 1450, 1048),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.failure is None
    assert result.rect == Rect(8, 1001, 169, 1047)       # shared 161px width
    assert result.rect is not None
    assert geometry.occupied is not None
    assert result.rect.right < geometry.occupied.left


def test_leading_edge_obstacle_pushes_the_sweep_past_it() -> None:
    # A Widgets surface (or anything else) that really sits at the left edge
    # is an obstacle, which is what replaced the blind 200px reserve.
    widgets = Rect(0, 1000, 120, 1048)
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(0, 1000, 1450, 1048),
        (widgets, Rect(900, 1000, 1450, 1048)),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect is not None
    assert result.rect.left >= widgets.right


def test_sits_flush_against_a_sibling_strip_on_the_left() -> None:
    sibling = Rect(8, 1000, 169, 1048)
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(8, 1000, 1450, 1048),
        (sibling, Rect(900, 1000, 1450, 1048)),
        (sibling,),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect == Rect(173, 1001, 334, 1047)     # sibling.right + 4px gap


def test_narrow_space_fails_instead_of_overlaying() -> None:
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(0, 1000, 1700, 1048),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect is None
    assert result.failure is PlacementFailure.NO_SPACE


def test_vertical_taskbar_is_rejected() -> None:
    result = place_taskbar_widget(
        TaskbarGeometry(Rect(0, 0, 48, 1080), Rect(0, 900, 48, 1080), None),
        dpi=96,
    )
    assert result.failure is PlacementFailure.VERTICAL


def test_complete_approved_surface_is_required() -> None:
    # 136px left of the notification area: less than the full 161px surface.
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(0, 1000, 1600, 1048),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect is None
    assert result.failure is PlacementFailure.NO_SPACE


def test_uses_verified_gap_before_start_when_right_side_is_full() -> None:
    geometry = TaskbarGeometry(
        Rect(0, 1528, 2560, 1600),
        Rect(2036, 1528, 2560, 1600),
        Rect(1152, 1528, 1812, 1600),
        (
            Rect(748, 1528, 816, 1600),
            Rect(819, 1528, 1149, 1600),
            Rect(1152, 1528, 1812, 1600),
        ),
    )

    result = place_taskbar_widget(geometry, dpi=144)

    assert result.rect == Rect(12, 1529, 254, 1598)    # 242 = 161 @ 144dpi


def test_sibling_usage_strip_is_not_covered() -> None:
    sibling = Rect(700, 1000, 897, 1048)
    geometry = TaskbarGeometry(
        Rect(0, 1000, 2560, 1048),
        Rect(2100, 1000, 2560, 1048),
        Rect(700, 1000, 2000, 1048),
        (sibling, Rect(900, 1000, 2000, 1048)),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect is not None
    assert result.rect.right <= sibling.left
    assert result.rect.left >= 8


def test_negative_monitor_coordinates_do_not_confuse_gap_with_failure() -> None:
    geometry = TaskbarGeometry(
        Rect(-1920, 1000, 0, 1048),
        Rect(-180, 1000, 0, 1048),
        Rect(-768, 1000, -108, 1048),
        (Rect(-1172, 1000, -1104, 1048), Rect(-768, 1000, -108, 1048)),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect == Rect(-1912, 1001, -1751, 1047)
