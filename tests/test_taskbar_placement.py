from codex_usage_widget.taskbar_placement import (
    PlacementFailure,
    Rect,
    TaskbarGeometry,
    place_taskbar_widget,
)


def test_places_widget_only_between_buttons_and_notification() -> None:
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(500, 1000, 1450, 1048),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.failure is None
    assert result.rect == Rect(1539, 1001, 1736, 1047)
    assert result.rect is not None
    assert geometry.occupied is not None
    assert result.rect.left >= geometry.occupied.right
    assert result.rect.right < geometry.notification.left


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
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(0, 1000, 1540, 1048),
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

    assert result.rect == Rect(446, 1529, 742, 1598)


def test_negative_monitor_coordinates_do_not_confuse_gap_with_failure() -> None:
    geometry = TaskbarGeometry(
        Rect(-1920, 1000, 0, 1048),
        Rect(-180, 1000, 0, 1048),
        Rect(-768, 1000, -108, 1048),
        (Rect(-1172, 1000, -1104, 1048), Rect(-768, 1000, -108, 1048)),
    )

    result = place_taskbar_widget(geometry, dpi=96)

    assert result.rect == Rect(-1373, 1001, -1176, 1047)
