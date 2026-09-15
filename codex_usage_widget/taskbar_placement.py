"""Pure geometry for placing a child inside unused taskbar space."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


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
    minimum = logical_pixels(minimum_width, dpi)
    preferred = logical_pixels(preferred_width, dpi)
    scaled_gap = logical_pixels(gap, dpi)
    # Start at the very edge: whatever actually sits there (a Widgets
    # surface, a left-aligned Start cluster) arrives in occupied_regions.
    leading_reserve = taskbar.left + logical_pixels(EDGE_MARGIN, dpi)
    source_regions = geometry.occupied_regions
    if not source_regions and geometry.occupied is not None:
        source_regions = (geometry.occupied,)
    regions = tuple(
        sorted(
            (
                region
                for region in source_regions
                if region.width > 0 and region.height > 0
            ),
            key=lambda region: region.left,
        )
    )
    anchors = {leading_reserve} | {
        sibling.right + scaled_gap for sibling in geometry.siblings
    }
    gap_left = leading_reserve
    left: int | None = None
    for region in (*regions, geometry.notification):
        gap_right = min(taskbar.right, region.left - scaled_gap)
        if gap_right - gap_left >= preferred:
            left = gap_left if gap_left in anchors else gap_right - preferred
            break
        gap_left = max(gap_left, region.right + scaled_gap)
    if left is None:
        # Nothing on the left: squeeze into the run before the tray icons.
        right = min(taskbar.right, geometry.notification.left - scaled_gap)
        occupied_right = taskbar.left
        if geometry.occupied is not None:
            occupied_right = max(taskbar.left, geometry.occupied.right)
        available = right - occupied_right
        if available < minimum:
            return PlacementResult(None, PlacementFailure.NO_SPACE)
        width = min(preferred, available)
        left = right - width
    else:
        width = preferred
    top = taskbar.top + max(0, (taskbar.height - height) // 2)
    return PlacementResult(Rect(left, top, left + width, top + height))
