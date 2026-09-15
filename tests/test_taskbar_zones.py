"""Zone, host and drag-drop placement rules (pure logic only)."""

import pytest

from codex_usage_widget.config import TaskbarHost, TaskbarZone, WidgetConfig
from codex_usage_widget.actions import set_edge_priority, set_taskbar_placement
from codex_usage_widget.taskbar_placement import (
    DRAGGED_STRIP_ALPHA,
    GHOST_ALPHA,
    OPAQUE_ALPHA,
    DragState,
    DropDecision,
    StartSlot,
    Rect,
    TaskbarGeometry,
    TaskbarHostCandidate,
    choose_host,
    clamp_to_host,
    decide_drop,
    drag_state,
    edge_anchor,
    ghost_rect,
    ghost_origin,
    evicted_from_edge,
    place_taskbar_widget,
    second_slot_left,
    start_slot,
)

DISPLAY2 = "\\\\.\\DISPLAY2"
PRIMARY = TaskbarHostCandidate(1, Rect(0, 1000, 1920, 1048), "", primary=True)
SECOND = TaskbarHostCandidate(2, Rect(1920, 1000, 3840, 1048), DISPLAY2)


def test_right_zone_is_the_mirror_of_left() -> None:
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(500, 1000, 1450, 1048),
    )

    left = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.LEFT)
    right = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.RIGHT)

    assert left.rect == Rect(8, 1001, 169, 1047)
    assert right.rect == Rect(1575, 1001, 1736, 1047)  # flush before the tray


def test_right_zone_sits_flush_left_of_a_sibling_in_the_same_zone() -> None:
    sibling = Rect(1575, 1000, 1736, 1048)
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(500, 1000, 1736, 1048),
        (Rect(500, 1000, 1300, 1048), sibling),
        (sibling,),
    )

    result = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.RIGHT)

    assert result.rect == Rect(1410, 1001, 1571, 1047)  # sibling.left - 4px gap


def test_zone_falls_back_to_the_other_end_when_its_own_is_full() -> None:
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(8, 1000, 1450, 1048),
        (Rect(8, 1000, 1450, 1048),),
    )

    result = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.LEFT)

    assert result.rect is not None
    assert result.rect.right <= 1736  # the run before the tray


def test_secondary_taskbar_without_a_tray_uses_its_own_right_edge() -> None:
    bar = Rect(1920, 1000, 3840, 1048)
    geometry = TaskbarGeometry(
        bar,
        Rect(bar.right, bar.top, bar.right, bar.bottom),  # no tray at all
        None,
        (Rect(2400, 1000, 2600, 1048),),
    )

    left = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.LEFT)
    right = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.RIGHT)

    assert left.rect == Rect(1928, 1001, 2089, 1047)
    assert right.rect == Rect(3671, 1001, 3832, 1047)


def test_claiming_the_edge_ignores_only_the_sibling_strips() -> None:
    sibling = Rect(8, 1000, 169, 1048)
    buttons = Rect(900, 1000, 1450, 1048)
    geometry = TaskbarGeometry(
        Rect(0, 1000, 1920, 1048),
        Rect(1740, 1000, 1920, 1048),
        Rect(8, 1000, 1450, 1048),
        (sibling, buttons),
        (sibling,),
    )

    polite = place_taskbar_widget(geometry, dpi=96, zone=TaskbarZone.LEFT)
    claimed = place_taskbar_widget(
        geometry, dpi=96, zone=TaskbarZone.LEFT, claim_edge=True
    )

    assert polite.rect == Rect(173, 1001, 334, 1047)  # beside the sibling
    assert claimed.rect == Rect(8, 1001, 169, 1047)  # the sibling's slot
    assert claimed.rect is not None
    assert claimed.rect.right <= buttons.left  # real buttons still respected


def test_host_choice_prefers_the_named_secondary_monitor() -> None:
    choice = choose_host(
        (PRIMARY, SECOND), host=TaskbarHost.SECONDARY, monitor=DISPLAY2
    )

    assert choice.candidate == SECOND
    assert choice.fallback is False


def test_host_choice_falls_back_to_primary_when_the_monitor_is_gone() -> None:
    choice = choose_host((PRIMARY,), host=TaskbarHost.SECONDARY, monitor=DISPLAY2)

    assert choice.candidate == PRIMARY
    assert choice.fallback is True


def test_host_choice_accepts_any_secondary_when_no_monitor_is_saved() -> None:
    choice = choose_host((PRIMARY, SECOND), host=TaskbarHost.SECONDARY, monitor="")

    assert choice.candidate == SECOND
    assert choice.fallback is False


def test_host_choice_reports_primary_directly() -> None:
    choice = choose_host((PRIMARY, SECOND), host=TaskbarHost.PRIMARY, monitor="")

    assert choice.candidate == PRIMARY
    assert choice.fallback is False


def test_drop_reads_host_and_zone_from_the_release_point() -> None:
    assert decide_drop((300, 1020), (PRIMARY, SECOND)) == DropDecision(
        PRIMARY, TaskbarZone.LEFT
    )
    assert decide_drop((1700, 1020), (PRIMARY, SECOND)) == DropDecision(
        PRIMARY, TaskbarZone.RIGHT
    )
    assert decide_drop((2000, 1020), (PRIMARY, SECOND)) == DropDecision(
        SECOND, TaskbarZone.LEFT
    )


def test_drop_outside_every_taskbar_keeps_the_current_placement() -> None:
    assert decide_drop((500, 400), (PRIMARY, SECOND)) is None


@pytest.mark.parametrize("x", [8, 20, 87, 88, 120, 168])
def test_drop_anywhere_on_a_left_sibling_claims_the_edge_slot(x: int) -> None:
    sibling = Rect(8, 1000, 169, 1048)

    inside = decide_drop((300, 1020), (PRIMARY,), siblings=(sibling,))
    swap = decide_drop((x, 1020), (PRIMARY,), siblings=(sibling,))

    assert inside == DropDecision(PRIMARY, TaskbarZone.LEFT, claim_edge=False)
    assert swap == DropDecision(
        PRIMARY, TaskbarZone.LEFT, claim_edge=True, edge_priority=True
    )


@pytest.mark.parametrize("x", [1575, 1600, 1655, 1656, 1700, 1735, 1800])
def test_drop_anywhere_on_a_right_sibling_claims_the_trailing_slot(x: int) -> None:
    sibling = Rect(1575, 1000, 1736, 1048)

    inside = decide_drop((1500, 1020), (PRIMARY,), siblings=(sibling,))
    swap = decide_drop((x, 1020), (PRIMARY,), siblings=(sibling,))

    assert inside == DropDecision(PRIMARY, TaskbarZone.RIGHT, claim_edge=False)
    assert swap == DropDecision(
        PRIMARY, TaskbarZone.RIGHT, claim_edge=True, edge_priority=True
    )


def test_a_sibling_on_another_taskbar_never_blocks_the_edge() -> None:
    far = Rect(1928, 1000, 2089, 1048)  # sits on the secondary taskbar

    decision = decide_drop((20, 1020), (PRIMARY, SECOND), siblings=(far,))

    assert decision == DropDecision(PRIMARY, TaskbarZone.LEFT, claim_edge=False)


def test_a_sibling_outside_the_host_vertical_band_is_ignored() -> None:
    above = Rect(8, 900, 169, 948)

    decision = decide_drop((20, 1020), (PRIMARY,), siblings=(above,))

    assert decision == DropDecision(PRIMARY, TaskbarZone.LEFT, claim_edge=False)


def test_left_edge_strip_dropped_on_inner_sibling_yields_its_slot() -> None:
    edge = Rect(8, 1000, 169, 1048)
    inner = Rect(173, 1000, 334, 1048)

    decision = decide_drop(
        (500, 1020),
        (PRIMARY,),
        siblings=(inner,),
        source=edge,
        final_rect=Rect(420, 1000, 581, 1048),
    )

    assert decision == DropDecision(
        PRIMARY,
        TaskbarZone.LEFT,
        claim_edge=False,
        edge_priority=False,
        yield_edge=True,
    )


def test_left_inner_strip_dropped_on_edge_sibling_claims_its_slot() -> None:
    edge = Rect(8, 1000, 169, 1048)
    inner = Rect(173, 1000, 334, 1048)

    decision = decide_drop(
        (20, 1020),
        (PRIMARY,),
        siblings=(edge,),
        source=inner,
        final_rect=Rect(-60, 1000, 101, 1048),
    )

    assert decision == DropDecision(
        PRIMARY, TaskbarZone.LEFT, claim_edge=True, edge_priority=True
    )


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        (
            Rect(8, 1000, 169, 1048),
            Rect(173, 1000, 334, 1048),
            DropDecision(
                PRIMARY, TaskbarZone.LEFT, edge_priority=False, yield_edge=True
            ),
        ),
        (
            Rect(173, 1000, 334, 1048),
            Rect(8, 1000, 169, 1048),
            DropDecision(
                PRIMARY,
                TaskbarZone.LEFT,
                claim_edge=True,
                edge_priority=True,
            ),
        ),
    ],
)
def test_full_overlap_keeps_the_existing_swap_gesture(
    source: Rect, target: Rect, expected: DropDecision
) -> None:
    decision = decide_drop(
        ((target.left + target.right) // 2, 1020),
        (PRIMARY,),
        siblings=(target,),
        source=source,
        final_rect=target,
    )

    assert decision == expected


def test_cross_host_drop_on_a_sibling_claims_the_target_slot() -> None:
    source = Rect(8, 1000, 169, 1048)
    target = Rect(1928, 1000, 2089, 1048)

    decision = decide_drop(
        (2000, 1020),
        (PRIMARY, SECOND),
        siblings=(target,),
        source=source,
        final_rect=Rect(1920, 1000, 2081, 1048),
    )

    assert decision == DropDecision(
        SECOND, TaskbarZone.LEFT, claim_edge=True, edge_priority=True
    )


@pytest.mark.parametrize("left", [254, 334, 400, 500])
def test_left_edge_strip_reorders_after_passing_inner_sibling(left: int) -> None:
    edge = Rect(8, 1000, 169, 1048)
    inner = Rect(173, 1000, 334, 1048)

    decision = decide_drop(
        (left + 80, 1020),
        (PRIMARY,),
        siblings=(inner,),
        source=edge,
        final_rect=Rect(left, 1000, left + 161, 1048),
    )

    assert decision == DropDecision(
        PRIMARY, TaskbarZone.LEFT, edge_priority=False, yield_edge=True
    )


def test_right_zone_reorder_is_the_mirror_of_left() -> None:
    edge = Rect(1575, 1000, 1736, 1048)
    inner = Rect(1410, 1000, 1571, 1048)

    outward = decide_drop(
        (1800, 1020),
        (PRIMARY,),
        siblings=(edge,),
        source=inner,
        final_rect=Rect(1720, 1000, 1881, 1048),
    )
    inward = decide_drop(
        (1250, 1020),
        (PRIMARY,),
        siblings=(inner,),
        source=edge,
        final_rect=Rect(1170, 1000, 1331, 1048),
    )

    assert outward == DropDecision(
        PRIMARY, TaskbarZone.RIGHT, claim_edge=True, edge_priority=True
    )
    assert inward == DropDecision(
        PRIMARY, TaskbarZone.RIGHT, edge_priority=False, yield_edge=True
    )


def test_drop_on_the_original_side_of_a_sibling_keeps_order() -> None:
    edge = Rect(8, 1000, 169, 1048)
    inner = Rect(173, 1000, 334, 1048)

    edge_stays = decide_drop(
        (80, 1020),
        (PRIMARY,),
        siblings=(inner,),
        source=edge,
        final_rect=Rect(0, 1000, 161, 1048),
    )
    inner_stays = decide_drop(
        (500, 1020),
        (PRIMARY,),
        siblings=(edge,),
        source=inner,
        final_rect=Rect(420, 1000, 581, 1048),
    )

    assert edge_stays == DropDecision(PRIMARY, TaskbarZone.LEFT)
    assert inner_stays == DropDecision(PRIMARY, TaskbarZone.LEFT)


def test_ghost_rect_makes_reorder_independent_of_grab_offset() -> None:
    source = Rect(8, 1000, 169, 1048)
    sibling = Rect(173, 1000, 334, 1048)
    from_left_grab = ghost_rect((410, 1020), (18, 1020), source)
    from_right_grab = ghost_rect((551, 1020), (159, 1020), source)

    assert from_left_grab == from_right_grab == Rect(400, 1000, 561, 1048)
    first = decide_drop(
        (410, 1020),
        (PRIMARY,),
        siblings=(sibling,),
        source=source,
        final_rect=from_left_grab,
    )
    second = decide_drop(
        (551, 1020),
        (PRIMARY,),
        siblings=(sibling,),
        source=source,
        final_rect=from_right_grab,
    )

    assert first == second == DropDecision(
        PRIMARY, TaskbarZone.LEFT, edge_priority=False, yield_edge=True
    )


def test_dragged_rect_stays_inside_its_host() -> None:
    host = Rect(0, 1000, 1920, 1048)

    assert clamp_to_host(Rect(-50, 1001, 111, 1047), host).left == 0
    assert clamp_to_host(Rect(1900, 1001, 2061, 1047), host).right == 1920


def test_placement_action_clears_the_monitor_for_a_primary_host() -> None:
    secondary = set_taskbar_placement(
        WidgetConfig(),
        zone=TaskbarZone.RIGHT,
        host=TaskbarHost.SECONDARY,
        monitor=DISPLAY2,
    )
    back = set_taskbar_placement(
        secondary, zone=TaskbarZone.LEFT, host=TaskbarHost.PRIMARY
    )

    assert secondary.taskbar_zone is TaskbarZone.RIGHT
    assert secondary.taskbar_host_monitor == DISPLAY2
    assert back.taskbar_host is TaskbarHost.PRIMARY
    assert back.taskbar_host_monitor == ""


def test_start_slot_gives_the_edge_to_the_priority_twin() -> None:
    assert start_slot(priority=True, sibling_seen=False, waited=0.0) is (
        StartSlot.CLAIM
    )
    assert start_slot(priority=True, sibling_seen=True, waited=99.0) is (
        StartSlot.CLAIM
    )


def test_start_slot_waits_in_the_second_slot_for_a_missing_sibling() -> None:
    assert start_slot(priority=False, sibling_seen=False, waited=0.0) is (
        StartSlot.RESERVE
    )
    assert start_slot(priority=False, sibling_seen=False, waited=9.9) is (
        StartSlot.RESERVE
    )
    # a solo install must not sit one slot away from the edge for ever
    assert start_slot(priority=False, sibling_seen=False, waited=10.0) is (
        StartSlot.SWEEP
    )
    # the sibling showed up: the ordinary sweep lands beside it
    assert start_slot(priority=False, sibling_seen=True, waited=0.0) is (
        StartSlot.SWEEP
    )


def test_edge_and_second_slots_mirror_each_other() -> None:
    bar = Rect(0, 1000, 1920, 1048)
    notify = Rect(1740, 1000, 1920, 1048)
    left_edge = edge_anchor(
        bar, notify, zone=TaskbarZone.LEFT, gap=4, margin=8, width=161
    )
    right_edge = edge_anchor(
        bar, notify, zone=TaskbarZone.RIGHT, gap=4, margin=8, width=161
    )

    assert left_edge == 8
    assert right_edge == 1575
    assert second_slot_left(
        bar, notify, zone=TaskbarZone.LEFT, gap=4, margin=8, width=161
    ) == 173
    assert second_slot_left(
        bar, notify, zone=TaskbarZone.RIGHT, gap=4, margin=8, width=161
    ) == 1410


def test_eviction_is_only_reported_when_a_sibling_took_the_edge() -> None:
    assert evicted_from_edge(
        was_at_edge=True, at_edge_now=False, sibling_at_edge=True
    )
    # moved off the edge for another reason (no sibling there): not an eviction
    assert not evicted_from_edge(
        was_at_edge=True, at_edge_now=False, sibling_at_edge=False
    )
    assert not evicted_from_edge(
        was_at_edge=False, at_edge_now=False, sibling_at_edge=True
    )
    assert not evicted_from_edge(
        was_at_edge=True, at_edge_now=True, sibling_at_edge=False
    )


def test_edge_priority_action_records_the_order() -> None:
    demoted = set_edge_priority(WidgetConfig(), priority=False)
    promoted = set_edge_priority(demoted, priority=True)

    assert WidgetConfig().taskbar_edge_priority is True   # Codex default
    assert demoted.taskbar_edge_priority is False
    assert promoted.taskbar_edge_priority is True


def test_ghost_follows_the_cursor_without_clamping() -> None:
    origin = Rect(173, 1033, 334, 1079)

    # grabbed 27px into the strip, dragged far onto the second monitor
    assert ghost_origin((2500, 900), (200, 1056), origin) == (2473, 877)
    # and to the left of the primary monitor: no clamping at all
    assert ghost_origin((-300, 1056), (200, 1056), origin) == (-327, 1033)


def test_drag_state_separates_a_click_from_a_drag() -> None:
    pressed = drag_state(DragState.IDLE, "press")
    assert pressed is DragState.PRESSED
    # small wobble stays a click
    assert drag_state(pressed, "move", beyond_threshold=False) is DragState.PRESSED
    assert drag_state(pressed, "release") is DragState.IDLE
    # past the threshold it becomes a drag and stays one until it ends
    dragging = drag_state(pressed, "move", beyond_threshold=True)
    assert dragging is DragState.DRAGGING
    assert drag_state(dragging, "move", beyond_threshold=False) is DragState.DRAGGING
    assert drag_state(dragging, "cancel") is DragState.IDLE
    assert drag_state(dragging, "release") is DragState.IDLE


def test_ghost_alphas_are_the_shared_contract() -> None:
    assert (GHOST_ALPHA, DRAGGED_STRIP_ALPHA, OPAQUE_ALPHA) == (153, 90, 255)
