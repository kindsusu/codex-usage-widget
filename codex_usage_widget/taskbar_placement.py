"""Pure geometry for placing a child inside unused taskbar space."""

from dataclasses import dataclass
from enum import StrEnum


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


class PlacementFailure(StrEnum):
    """Reason a real embedded placement cannot be made."""

    VERTICAL = "vertical"
    NO_SPACE = "no_space"


@dataclass(frozen=True, slots=True)
class PlacementResult:
    """Either a safe placement or a failure reason."""

    rect: Rect | None
    failure: PlacementFailure | None = None


def logical_pixels(value: int, dpi: int) -> int:
    """Scale logical pixels using the target taskbar DPI."""
    return max(1, (value * max(96, dpi) + 48) // 96)


def place_taskbar_widget(  # noqa: PLR0913
    geometry: TaskbarGeometry,
    *,
    dpi: int,
    preferred_width: int = 197,
    minimum_width: int = 197,
    maximum_height: int = 46,
    gap: int = 4,
) -> PlacementResult:
    """Choose unused space immediately before the notification area."""
    taskbar = geometry.taskbar
    if taskbar.height > taskbar.width:
        return PlacementResult(None, PlacementFailure.VERTICAL)
    height = min(taskbar.height, logical_pixels(maximum_height, dpi))
    if height < logical_pixels(32, dpi):
        return PlacementResult(None, PlacementFailure.NO_SPACE)
    right = min(
        taskbar.right,
        geometry.notification.left - logical_pixels(gap, dpi),
    )
    occupied_right = taskbar.left
    if geometry.occupied is not None:
        occupied_right = max(taskbar.left, geometry.occupied.right)
    available = right - occupied_right
    minimum = logical_pixels(minimum_width, dpi)
    preferred = logical_pixels(preferred_width, dpi)
    if available >= minimum:
        width = min(preferred, available)
        left = right - width
    else:
        # Windows reserves the leading edge for Widgets even when UIA does not
        # expose a button. Search only gaps after that conservative boundary.
        leading_reserve = taskbar.left + logical_pixels(200, dpi)
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
        gap_left = leading_reserve
        left: int | None = None
        for region in (*regions, geometry.notification):
            gap_right = min(taskbar.right, region.left - logical_pixels(gap, dpi))
            if gap_right - gap_left >= preferred:
                left = gap_right - preferred
                break
            gap_left = max(gap_left, region.right + logical_pixels(gap, dpi))
        if left is None:
            return PlacementResult(None, PlacementFailure.NO_SPACE)
        width = preferred
        right = left + width
    top = taskbar.top + max(0, (taskbar.height - height) // 2)
    return PlacementResult(Rect(left, top, right, top + height))
