"""Pure geometry for placing a child inside unused taskbar space.

SHARED STRIP CONTRACT -- the zone/host rules and the 161px width here are
mirrored in the Claude widget (widget.pyw, the ``_tb_*`` block). Change both
or the two strips stop behaving like siblings.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from codex_usage_widget.config import TaskbarHost, TaskbarZone


@dataclass(frozen=True, slots=True)
class Rect:
    """A screen-coordinate rectangle."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        """Return a nonnegative width."""
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        """Return a nonnegative height."""
        return max(0, self.bottom - self.top)


@dataclass(frozen=True, slots=True)
class TaskbarGeometry:
    """Bounds relevant to a safe taskbar placement."""

    taskbar: Rect
    notification: Rect
    occupied: Rect | None
    occupied_regions: tuple[Rect, ...] = ()
    # Sibling usage strips (also inside occupied_regions). A free run that
    # starts at one of them is where this strip should sit, flush against it.
    siblings: tuple[Rect, ...] = ()


class PlacementFailure(StrEnum):
    """Reason a real embedded placement cannot be made."""

    VERTICAL = "vertical"
    NO_SPACE = "no_space"


@dataclass(frozen=True, slots=True)
class PlacementResult:
    """Either a safe placement or a failure reason."""

    rect: Rect | None
    failure: PlacementFailure | None = None


# Left sweep start. Until 2026-09-15 this was a flat 200px "Windows reserves
# the leading edge for Widgets" rule, which threw away the whole left end of a
# taskbar that has no Widgets button. Now only a hairline margin is skipped and
# anything that really sits there arrives in `occupied_regions` (the native
# scan treats every element starting inside the leading band as an obstacle,
# whatever its UIA control type). Mirrored in the Claude widget.
EDGE_MARGIN: Final = 8
LEADING_BAND: Final = 200
# SHARED STRIP CONTRACT -- deterministic sibling order without any IPC.
# Exactly one twin owns the edge: ``taskbar_edge_priority`` defaults to True
# here and False in the Claude widget, which preserves the approved layout
# (Codex at the edge, Claude beside it) across reboots no matter which one
# starts first. A strip without priority waits this long for its sibling to
# appear before taking the edge itself, so a solo install never sits one slot
# away from the edge for good.
EDGE_HOLD_SECONDS: Final = 10.0
# A claim the sibling refuses to honour means both strips want the same slot.
# Nobody can see the other's settings, so the contest is resolved from three
# facts each side knows about ITSELF: was I just dragged here, am I the static
# tie-break winner, and how long have I been running.
# Two scans (~3s) is enough evidence of a real contest while still
# surviving a single bad UIA read; longer leaves the strips visibly
# overlapped after a drag.
CLAIM_YIELD_SCANS: Final = 2
# A drag-claim outranks everything for this long -- long enough for the other
# side to notice the contest and step aside.
EDGE_EXPLICIT_SECONDS: Final = 30.0
# A contest inside this window after startup is a boot race, not a user
# action, so the static winner keeps the slot. Later contests mean the user
# just dragged the sibling onto it, and even the winner gives way.
EDGE_STARTUP_GRACE: Final = 15.0
# Codex owns the static tie-break; the Claude widget sets this False.
EDGE_TIE_BREAK_WINNER: Final = True


def logical_pixels(value: int, dpi: int) -> int:
    """Scale logical pixels using the target taskbar DPI."""
    return max(1, (value * max(96, dpi) + 48) // 96)


def place_taskbar_widget(  # noqa: PLR0913
    geometry: TaskbarGeometry,
    *,
    dpi: int,
    # 30 mark + 4 gap + 127 usage block — the shared strip width, identical in
    # the Claude widget so the two strips render as twins (2026-09-14).
    preferred_width: int = 161,
    minimum_width: int = 161,
    maximum_height: int = 46,
    gap: int = 4,
    zone: TaskbarZone = TaskbarZone.LEFT,
    claim_edge: bool = False,
) -> PlacementResult:
    """Choose the leftmost free run, falling back to the notification area.

    The user wants both usage strips packed at the left of the taskbar
    (2026-09-14), so the free runs are swept left to right and the first one
    that fits wins. A run that begins at the leading edge margin or at a
    sibling strip is taken flush with that anchor, which is what puts the two
    strips side by side; any other run still hugs the obstacle on its right.
    """
    taskbar = geometry.taskbar
    if taskbar.height > taskbar.width:
        return PlacementResult(None, PlacementFailure.VERTICAL)
    height = min(taskbar.height, logical_pixels(maximum_height, dpi))
    if height < logical_pixels(32, dpi):
        return PlacementResult(None, PlacementFailure.NO_SPACE)
    preferred = max(
        logical_pixels(preferred_width, dpi), logical_pixels(minimum_width, dpi)
    )
    scaled_gap = logical_pixels(gap, dpi)
    margin = logical_pixels(EDGE_MARGIN, dpi)
    siblings = () if claim_edge else geometry.siblings
    regions = _obstacles(geometry, siblings=siblings)
    runs = free_runs(
        taskbar,
        geometry.notification,
        regions,
        gap=scaled_gap,
        margin=margin,
    )
    left = _select(
        runs,
        zone=zone,
        preferred=preferred,
        left_anchors={taskbar.left + margin}
        | {sibling.right + scaled_gap for sibling in siblings},
        right_anchors={
            min(taskbar.right - margin, geometry.notification.left - scaled_gap)
        }
        | {sibling.left - scaled_gap for sibling in siblings},
    )
    if left is None:
        return PlacementResult(None, PlacementFailure.NO_SPACE)
    top = taskbar.top + max(0, (taskbar.height - height) // 2)
    return PlacementResult(Rect(left, top, left + preferred, top + height))


def _obstacles(
    geometry: TaskbarGeometry, *, siblings: tuple[Rect, ...]
) -> tuple[Rect, ...]:
    """Every rect the strip must not cover, left to right."""
    source = geometry.occupied_regions
    if not source and geometry.occupied is not None:
        source = (geometry.occupied,)
    if geometry.siblings and not siblings:
        # Claiming the edge: ignore the sibling strips so the sweep can take
        # the slot they hold. They see us on their next scan and step aside.
        dropped = {(s.left, s.right) for s in geometry.siblings}
        source = tuple(r for r in source if (r.left, r.right) not in dropped)
    return tuple(
        sorted(
            (region for region in source if region.width > 0 and region.height > 0),
            key=lambda region: region.left,
        )
    )


def free_runs(
    taskbar: Rect,
    notification: Rect,
    regions: tuple[Rect, ...],
    *,
    gap: int,
    margin: int,
) -> tuple[tuple[int, int], ...]:
    """(start, end) of every free horizontal run between the two edges.

    Both ends are measured, never assumed: secondary taskbars carry no tray at
    all, so the trailing run simply ends at the taskbar's own edge margin.
    """
    runs: list[tuple[int, int]] = []
    cursor = taskbar.left + margin
    for region in (*regions, notification):
        edge = min(taskbar.right - margin, region.left - gap)
        if edge > cursor:
            runs.append((cursor, edge))
        cursor = max(cursor, region.right + gap)
    limit = taskbar.right - margin
    if limit > cursor:
        runs.append((cursor, limit))
    return tuple(runs)


def _select(
    runs: tuple[tuple[int, int], ...],
    *,
    zone: TaskbarZone,
    preferred: int,
    left_anchors: set[int],
    right_anchors: set[int],
) -> int | None:
    """Left coordinate of the chosen run, or None when nothing fits.

    Runs are scanned in the zone's own direction and the first one that fits
    wins, so a left strip with no room on the left still lands before the tray
    (exactly what it did before zones existed) and a right strip with no room
    there falls back toward the leading edge.
    """
    forward = [run for run in runs if run[1] - run[0] >= preferred]
    if not forward:
        return None
    ordered = forward if zone is TaskbarZone.LEFT else list(reversed(forward))
    start, end = ordered[0]
    if zone is TaskbarZone.LEFT:
        return start if start in left_anchors else end - preferred
    return end - preferred if end in right_anchors else start


# ---- host selection and drag/drop decisions (pure) -------------------------
# SHARED STRIP CONTRACT -- mirrored in the Claude widget.


@dataclass(frozen=True, slots=True)
class TaskbarHostCandidate:
    """One taskbar window the strip could be embedded into."""

    handle: int
    bounds: Rect
    monitor: str = ""
    primary: bool = False


@dataclass(frozen=True, slots=True)
class HostChoice:
    """The taskbar to embed into, and whether that was the requested one."""

    candidate: TaskbarHostCandidate | None
    fallback: bool = False


def choose_host(
    candidates: tuple[TaskbarHostCandidate, ...],
    *,
    host: TaskbarHost,
    monitor: str,
) -> HostChoice:
    """Resolve the configured host against the taskbars that exist now.

    An unplugged secondary monitor falls back to the primary taskbar WITHOUT
    touching the saved setting, so the strip returns to the chosen screen by
    itself once the monitor is back.
    """
    primary = next((item for item in candidates if item.primary), None)
    if host is TaskbarHost.PRIMARY:
        return HostChoice(primary, fallback=primary is None)
    wanted = monitor.casefold()
    secondary = next(
        (
            item
            for item in candidates
            if not item.primary and (not wanted or item.monitor.casefold() == wanted)
        ),
        None,
    )
    if secondary is not None:
        return HostChoice(secondary)
    return HostChoice(primary, fallback=True)


@dataclass(frozen=True, slots=True)
class DropDecision:
    """Where a dragged strip should live once the button is released."""

    host: TaskbarHostCandidate
    zone: TaskbarZone
    claim_edge: bool = False
    edge_priority: bool | None = None
    yield_edge: bool = False


def decide_drop(
    point: tuple[int, int],
    candidates: tuple[TaskbarHostCandidate, ...],
    *,
    siblings: tuple[Rect, ...] = (),
    source: Rect | None = None,
    final_rect: Rect | None = None,
) -> DropDecision | None:
    """Read a released drag: which taskbar, which end, whose slot.

    Returns None when the strip was dropped outside every taskbar, which the
    caller treats as "keep the previous placement".
    """
    x, y = point
    if final_rect is not None:
        x = (final_rect.left + final_rect.right) // 2
        y = (final_rect.top + final_rect.bottom) // 2
    host = next(
        (
            item
            for item in candidates
            if item.bounds.left <= x < item.bounds.right
            and item.bounds.top <= y < item.bounds.bottom
        ),
        None,
    )
    if host is None:
        return None
    middle = (host.bounds.left + host.bounds.right) // 2
    zone = TaskbarZone.LEFT if x < middle else TaskbarZone.RIGHT
    inside = tuple(
        sibling
        for sibling in siblings
        if sibling.left < host.bounds.right and sibling.right > host.bounds.left
        and sibling.top < host.bounds.bottom
        and sibling.bottom > host.bounds.top
    )
    # The sibling's whole surface is a swap target.  Requiring the pointer to
    # cross its midpoint made half of the visible strip a misleading dead zone.
    # Points farther toward the outer edge keep the existing edge-claim gesture.
    if zone is TaskbarZone.LEFT:
        same_zone = tuple(
            item for item in inside if (item.left + item.right) // 2 < middle
        )
        claim = bool(same_zone) and x < min(item.right for item in same_zone)
    else:
        same_zone = tuple(
            item for item in inside if (item.left + item.right) // 2 >= middle
        )
        claim = bool(same_zone) and x >= max(item.left for item in same_zone)
    if same_zone and source is not None and final_rect is not None:
        source_on_host = (
            source.left < host.bounds.right
            and source.right > host.bounds.left
            and source.top < host.bounds.bottom
            and source.bottom > host.bounds.top
        )
        if not source_on_host:
            return DropDecision(
                host, zone, claim, edge_priority=True if claim else None
            )
        source_middle = (source.left + source.right) // 2
        final_middle = (final_rect.left + final_rect.right) // 2
        target = min(
            same_zone,
            key=lambda item: abs((item.left + item.right) // 2 - source_middle),
        )
        target_middle = (target.left + target.right) // 2
        source_at_edge = (
            source_middle < target_middle
            if zone is TaskbarZone.LEFT
            else source_middle > target_middle
        )
        final_at_edge = (
            final_middle < target_middle
            if zone is TaskbarZone.LEFT
            else final_middle > target_middle
        )
        overlaps_target = (
            final_rect.left < target.right
            and final_rect.right > target.left
            and final_rect.top < target.bottom
            and final_rect.bottom > target.top
        )
        if overlaps_target:
            # Preserve the established direct-overlap swap gesture. In
            # particular, equal centers have no geometric "side" of their own.
            final_at_edge = not source_at_edge
        if source_at_edge == final_at_edge:
            return DropDecision(host, zone)
        if source_at_edge:
            return DropDecision(
                host, zone, claim_edge=False, edge_priority=False, yield_edge=True
            )
        return DropDecision(host, zone, claim_edge=True, edge_priority=True)
    return DropDecision(host, zone, claim, edge_priority=True if claim else None)


def clamp_to_host(rect: Rect, host: Rect) -> Rect:
    """Keep a dragged strip inside its taskbar, width unchanged."""
    width = rect.width
    left = max(host.left, min(rect.left, host.right - width))
    return Rect(left, rect.top, left + width, rect.bottom)


# ---- deterministic start slot (pure) --------------------------------------
# SHARED STRIP CONTRACT -- mirrored in the Claude widget.


def edge_anchor(  # noqa: PLR0913
    taskbar: Rect,
    notification: Rect,
    *,
    zone: TaskbarZone,
    gap: int,
    margin: int,
    width: int,
) -> int:
    """Left coordinate of the slot flush with the zone's outer edge."""
    if zone is TaskbarZone.LEFT:
        return taskbar.left + margin
    return min(taskbar.right - margin, notification.left - gap) - width


def second_slot_left(  # noqa: PLR0913
    taskbar: Rect,
    notification: Rect,
    *,
    zone: TaskbarZone,
    gap: int,
    margin: int,
    width: int,
) -> int:
    """Left coordinate of the slot a sibling would leave for us."""
    anchor = edge_anchor(
        taskbar, notification, zone=zone, gap=gap, margin=margin, width=width
    )
    if zone is TaskbarZone.LEFT:
        return anchor + width + gap
    return anchor - width - gap


class StartSlot(StrEnum):
    """What a strip should do with the edge slot on this scan."""

    CLAIM = "claim"          # take the edge, pushing a sibling aside
    RESERVE = "reserve"      # hold the second slot, waiting for the sibling
    SWEEP = "sweep"          # ordinary measured placement


def start_slot(
    *,
    priority: bool,
    sibling_seen: bool,
    waited: float,
    hold: float = EDGE_HOLD_SECONDS,
) -> StartSlot:
    """Decide how this strip competes for the edge on this scan."""
    if priority:
        return StartSlot.CLAIM
    if sibling_seen:
        return StartSlot.SWEEP      # the sweep lands beside the sibling
    if waited < hold:
        return StartSlot.RESERVE    # keep the edge free a little longer
    return StartSlot.SWEEP


def evicted_from_edge(
    *, was_at_edge: bool, at_edge_now: bool, sibling_at_edge: bool
) -> bool:
    """True when a sibling's claim has just taken our edge slot."""
    return was_at_edge and not at_edge_now and sibling_at_edge


def should_yield_edge(
    *,
    contested: bool,
    explicit_recent: bool,
    tie_break_winner: bool,
    uptime: float,
    grace: float = EDGE_STARTUP_GRACE,
) -> bool:
    """Whether this strip must give up its edge claim.

    SHARED STRIP CONTRACT. The rules are ordered so that exactly one side
    yields in every combination, with no message passing:

    * a strip the user just dragged onto the edge never yields;
    * the tie-break loser (Claude) always yields a contested claim;
    * the winner (Codex) yields only when the contest starts after its own
      startup grace, which is precisely when a user drag caused it.
    """
    if not contested:
        return False
    if explicit_recent:
        return False
    if not tie_break_winner:
        return True
    return uptime > grace


# ---- drag ghost (pure) -----------------------------------------------------
# SHARED STRIP CONTRACT -- mirrored in the Claude widget.
# Standard drag-and-drop feel: the strip stays put and dims, while a
# click-through copy of its own bitmap follows the cursor across every
# monitor. Both alphas are SourceConstantAlpha values for UpdateLayeredWindow.
GHOST_ALPHA: Final = 153        # 60% -- the copy under the cursor
DRAGGED_STRIP_ALPHA: Final = 90  # 35% -- the original, left behind
OPAQUE_ALPHA: Final = 255


class DragState(StrEnum):
    """Pointer phases of a strip drag."""

    IDLE = "idle"
    PRESSED = "pressed"
    DRAGGING = "dragging"


def ghost_origin(
    cursor: tuple[int, int],
    press: tuple[int, int],
    origin: Rect,
) -> tuple[int, int]:
    """Top-left of the ghost: the cursor minus where inside it was grabbed.

    Deliberately unclamped -- the ghost may cross to any monitor, which is
    exactly what tells the user a drop over there is possible.
    """
    return (
        origin.left + cursor[0] - press[0],
        origin.top + cursor[1] - press[1],
    )


def ghost_rect(
    cursor: tuple[int, int],
    press: tuple[int, int],
    origin: Rect,
) -> Rect:
    """Final ghost bounds, preserving where inside the strip it was grabbed."""
    left, top = ghost_origin(cursor, press, origin)
    return Rect(left, top, left + origin.width, top + origin.height)


def drag_state(
    state: DragState, event: str, *, beyond_threshold: bool = False
) -> DragState:
    """Next pointer phase. One place so both widgets agree on click vs drag."""
    if event in {"cancel", "release"}:
        return DragState.IDLE
    if event == "press":
        return DragState.PRESSED
    if event == "move":
        if state is DragState.PRESSED and beyond_threshold:
            return DragState.DRAGGING
        return state
    return state
