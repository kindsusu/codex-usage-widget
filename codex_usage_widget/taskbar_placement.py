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


def decide_drop(
    point: tuple[int, int],
    candidates: tuple[TaskbarHostCandidate, ...],
    *,
    siblings: tuple[Rect, ...] = (),
) -> DropDecision | None:
    """Read a released drag: which taskbar, which end, whose slot.

    Returns None when the strip was dropped outside every taskbar, which the
    caller treats as "keep the previous placement".
    """
    x, y = point
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
    )
    # Dropped on the sibling's edge-facing half (or past it): the user aimed at
    # that slot, so take it. Dropped on its inner half: sit beside it instead.
    if zone is TaskbarZone.LEFT:
        same_zone = tuple(
            item for item in inside if (item.left + item.right) // 2 < middle
        )
        claim = bool(same_zone) and x < min(
            (item.left + item.right) // 2 for item in same_zone
        )
    else:
        same_zone = tuple(
            item for item in inside if (item.left + item.right) // 2 >= middle
        )
        claim = bool(same_zone) and x > max(
            (item.left + item.right) // 2 for item in same_zone
        )
    return DropDecision(host, zone, claim)


def clamp_to_host(rect: Rect, host: Rect) -> Rect:
    """Keep a dragged strip inside its taskbar, width unchanged."""
    width = rect.width
    left = max(host.left, min(rect.left, host.right - width))
    return Rect(left, rect.top, left + width, rect.bottom)
