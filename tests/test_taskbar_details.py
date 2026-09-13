from codex_usage_widget.taskbar_details import bounded_popup_position
from codex_usage_widget.window_runtime import format_window_position


def test_popup_is_clamped_to_monitor_bounds() -> None:
    bounds = (-1920, -100, 0, 980)

    assert bounded_popup_position(-1910, 970, 292, 200, bounds) == (-1920, 762)
    assert bounded_popup_position(-5, 10, 292, 200, bounds) == (-292, -100)


def test_popup_geometry_keeps_negative_coordinates_top_left_anchored() -> None:
    assert f"438x300{format_window_position(-1600, -80)}" == "438x300+-1600+-80"
