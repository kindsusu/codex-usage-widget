# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportMissingImports=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# comtypes.gen modules are generated at runtime, so the UIA block below is
# unresolvable on a fresh environment; suppressed like topmost.py.
"""Win32 implementation of the real taskbar child surface."""

from __future__ import annotations

import ctypes
import importlib
import sys
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from threading import Event, Lock, Thread, get_ident
from typing import TYPE_CHECKING, Final, Literal, Protocol, final

if TYPE_CHECKING:
    from collections.abc import Callable

    from PIL import Image

    from codex_usage_widget.taskbar_render import HitRegion

from codex_usage_widget.taskbar_model import TaskbarModel
from codex_usage_widget.taskbar_placement import (
    Rect,
    TaskbarGeometry,
    place_taskbar_widget,
)

WM_DESTROY: Final = 0x0002
WM_PAINT: Final = 0x000F
WM_ERASEBKGND: Final = 0x0014
WM_LBUTTONUP: Final = 0x0202
WM_RBUTTONUP: Final = 0x0205
WM_MOUSEMOVE: Final = 0x0200
WM_MOUSELEAVE: Final = 0x02A3
WM_APP_UPDATE: Final = 0x8001
WM_APP_VISIBILITY: Final = 0x8002
WM_APP_STOP: Final = 0x8003
WM_APP_LAYOUT: Final = 0x8004
WS_CHILD: Final = 0x40000000
WS_POPUP: Final = 0x80000000
WS_CLIPSIBLINGS: Final = 0x04000000
WS_EX_LAYERED: Final = 0x00080000
WS_EX_NOACTIVATE: Final = 0x08000000
WS_EX_TOOLWINDOW: Final = 0x00000080
GWL_STYLE: Final = -16
ULW_ALPHA: Final = 0x2
SW_HIDE: Final = 0
SW_SHOWNOACTIVATE: Final = 4
SWP_NOACTIVATE: Final = 0x0010
SWP_FRAMECHANGED: Final = 0x0020
SPI_GETHIGHCONTRAST: Final = 0x0042
HCF_HIGHCONTRASTON: Final = 0x1
_TIMER_MS: Final = 1_500
_COINIT_MULTITHREADED: Final = 0
_RPC_E_CHANGED_MODE: Final = -2_147_417_850
_TME_LEAVE: Final = 0x2
_AC_SRC_ALPHA: Final = 0x1
_DIB_RGB_COLORS: Final = 0
_UIA_BUTTON_CONTROL_TYPE: Final = 50_000
_VK_LBUTTON: Final = 0x01

LRESULT = wintypes.LPARAM
_callback_factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = _callback_factory(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


@final
class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


@final
class _PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", _RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


@final
class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


@final
class _HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwFlags", wintypes.DWORD),
        ("lpszDefaultScheme", wintypes.LPWSTR),
    ]


@final
class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


@final
class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


@final
class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


@final
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


@final
class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


@final
class _TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("hwndTrack", wintypes.HWND),
        ("dwHoverTime", wintypes.DWORD),
    ]


class _AttachmentApi(Protocol):
    def get_style(self, hwnd: int) -> int: ...
    def set_style(self, hwnd: int, style: int) -> None: ...
    def get_parent(self, hwnd: int) -> int: ...
    def set_parent(self, hwnd: int, parent: int) -> None: ...
    def position(self, hwnd: int, parent: int, rect: Rect, origin: Rect) -> None: ...


def attach_transaction(
    api: _AttachmentApi, hwnd: int, parent: int, rect: Rect, origin: Rect
) -> bool:
    """Attach and verify, restoring the original window state on failure."""
    original_style = api.get_style(hwnd)
    original_parent = api.get_parent(hwnd)
    child_style = (original_style & ~WS_POPUP) | WS_CHILD | WS_CLIPSIBLINGS
    try:
        api.set_style(hwnd, child_style)
        if api.get_style(hwnd) != child_style:
            raise OSError  # noqa: TRY301
        api.set_parent(hwnd, parent)
        if api.get_parent(hwnd) != parent:
            raise OSError  # noqa: TRY301
        api.position(hwnd, parent, rect, origin)
    except OSError:
        try:
            api.set_parent(hwnd, original_parent)
            api.set_style(hwnd, original_style)
        except OSError:
            pass
        return False
    return True


@dataclass(frozen=True, slots=True)
class _Target:
    parent: int
    bounds: Rect
    placement: Rect
    dpi: int


@final
class NativeTaskbarHost:
    """Own a child HWND and all native calls on a private message thread."""

    def __init__(
        self,
        on_details: Callable[[int, int], None],
        on_visibility: Callable[[int, int], None],
        on_menu: Callable[[int, int], None] | None = None,
    ) -> None:
        """Bind callbacks and initialize thread-safe state."""
        self._on_details = on_details
        self._on_visibility = on_visibility
        self._on_menu = on_visibility if on_menu is None else on_menu
        self._lock = Lock()
        self._ready = Event()
        self._stop_requested = Event()
        self._generation = 0
        self._thread: Thread | None = None
        self._observer: Thread | None = None
        self._model = TaskbarModel((), "Codex", "불러오는 중", None, False)
        self._visible = True
        self._available = False
        self._attached = False
        self._hwnd = 0
        self._thread_id = 0
        self._wndproc: object | None = None
        self._hover_region: Literal["usage", "menu"] | None = None
        self._suppress_menu_release = False
        self._observed_target: _Target | None = None

    @property
    def available(self) -> bool:
        """Return whether the worker and HWND initialized."""
        with self._lock:
            return self._available

    @property
    def attached(self) -> bool:
        """Return whether the HWND has a verified taskbar parent."""
        with self._lock:
            return self._attached

    @property
    def hwnd(self) -> int:
        """Return the owned HWND, or zero before initialization."""
        with self._lock:
            return self._hwnd

    def start(self) -> bool:
        """Start once; wait only for the bounded initial thread bootstrap."""
        if sys.platform != "win32":
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._ready.clear()
            self._generation += 1
            generation = self._generation
            stop_event = Event()
            self._stop_requested = stop_event
            self._suppress_menu_release = False
            self._thread = Thread(
                target=self._run,
                args=(stop_event, generation),
                name="taskbar-widget",
                daemon=True,
            )
            self._thread.start()
        _ = self._ready.wait(0.75)
        return self.available

    def update(self, model: TaskbarModel) -> None:
        """Publish a model and schedule repaint."""
        with self._lock:
            if model == self._model:
                return
            self._model = model
            hwnd = self._hwnd
        if hwnd:
            _user32().PostMessageW(hwnd, WM_APP_UPDATE, 0, 0)

    def set_visible(self, visible: bool) -> None:
        """Schedule an effective visibility change."""
        with self._lock:
            if visible == self._visible:
                return
            self._visible = visible
            hwnd = self._hwnd
        if hwnd:
            _user32().PostMessageW(hwnd, WM_APP_VISIBILITY, int(visible), 0)

    def suppress_held_menu_release(self) -> bool:
        """Consume the release of a press that just dismissed the popup."""
        with self._lock:
            hwnd = self._hwnd
        if not hwnd:
            return False
        user32 = _user32()
        if not user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000:
            return False
        point = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return False
        if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
            return False
        if self._region_at(hwnd, point.x, point.y) != "menu":
            return False
        with self._lock:
            self._suppress_menu_release = True
        return True

    def menu_button_contains_screen(self, x: int, y: int) -> bool:
        """Return whether a screen point is inside the current Codex button."""
        with self._lock:
            hwnd = self._hwnd
        if not hwnd:
            return False
        point = wintypes.POINT(x, y)
        if not _user32().ScreenToClient(hwnd, ctypes.byref(point)):
            return False
        return self._region_at(hwnd, point.x, point.y) == "menu"

    def stop(self) -> None:
        """Destroy the HWND and join the worker for a bounded duration."""
        with self._lock:
            thread = self._thread
            hwnd = self._hwnd
            self._stop_requested.set()
        if hwnd:
            _user32().PostMessageW(hwnd, WM_APP_STOP, 0, 0)
        if thread is not None and thread.ident != get_ident():
            thread.join(timeout=2.0)
        observer = self._observer
        if observer is not None and observer.ident != get_ident():
            observer.join(timeout=0.25)
        with self._lock:
            if thread is not None and thread.is_alive():
                return
            self._thread = None
            self._observer = None
            self._available = False
            self._attached = False
            self._hwnd = 0

    def _run(self, stop_event: Event, generation: int) -> None:
        user32 = _user32()
        # Keep Win32 and UIA rectangles in the same physical coordinate space.
        _ = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"CodexUsageTaskbar_{id(self):x}"
        wndproc = WNDPROC(self._window_proc)
        self._wndproc = wndproc
        wc = _WNDCLASSW(
            lpfnWndProc=wndproc,
            hInstance=hinstance,
            lpszClassName=class_name,
        )
        atom = 0
        hwnd = 0
        try:
            atom = int(user32.RegisterClassW(ctypes.byref(wc)))
            if not atom or stop_event.is_set():
                return
            hwnd = int(
                user32.CreateWindowExW(
                    WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                    class_name,
                    "Codex usage",
                    WS_POPUP,
                    0,
                    0,
                    1,
                    1,
                    None,
                    None,
                    hinstance,
                    None,
                )
                or 0
            )
            if not hwnd or stop_event.is_set():
                return
            with self._lock:
                self._hwnd = hwnd
                self._available = True
                self._thread_id = kernel32.GetCurrentThreadId()
            self._update_accessible_name(hwnd)
            if stop_event.is_set():
                return
            self._observer = Thread(
                target=self._observe_taskbar,
                args=(hwnd, stop_event, generation),
                name="taskbar-observer",
                daemon=True,
            )
            self._observer.start()
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:  # noqa: BLE001
            return
        finally:
            stop_event.set()
            if hwnd and user32.IsWindow(hwnd):
                user32.DestroyWindow(hwnd)
            if atom:
                user32.UnregisterClassW(class_name, hinstance)
            with self._lock:
                if generation == self._generation:
                    self._available = False
                    self._attached = False
                    self._hwnd = 0
                    self._ready.set()

    def _window_proc(  # noqa: C901, PLR0911, PLR0912
        self, hwnd: int, message: int, wparam: int, lparam: int
    ) -> int:
        user32 = _user32()
        if message == WM_PAINT:
            paint = _PAINTSTRUCT()
            _user32().BeginPaint(hwnd, ctypes.byref(paint))
            _user32().EndPaint(hwnd, ctypes.byref(paint))
            return 0
        if message == WM_ERASEBKGND:
            return 1
        if message == WM_MOUSEMOVE:
            self._handle_mouse_move(hwnd, lparam)
            return 0
        if message == WM_MOUSELEAVE:
            with self._lock:
                self._suppress_menu_release = False
            self._set_hover(None)
            return 0
        if message in (WM_LBUTTONUP, WM_RBUTTONUP):
            if message == WM_LBUTTONUP:
                with self._lock:
                    suppress_release = self._suppress_menu_release
                    self._suppress_menu_release = False
                if suppress_release:
                    return 0
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            local_x = ctypes.c_short(lparam & 0xFFFF).value
            local_y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            region = self._region_at(hwnd, local_x, local_y)
            if region is None:
                return 0
            callback = self._on_menu
            if message == WM_LBUTTONUP:
                callback = (
                    self._on_details if region == "usage" else self._on_visibility
                )
            with suppress(Exception):
                callback(point.x, point.y)
            return 0
        if message == WM_APP_UPDATE:
            self._update_accessible_name(hwnd)
            self._render_layered(hwnd)
            return 0
        if message == WM_APP_VISIBILITY:
            self._apply_visibility()
            return 0
        if message == WM_APP_LAYOUT:
            self._apply_observed_target()
            return 0
        if message == WM_APP_STOP:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _handle_mouse_move(self, hwnd: int, lparam: int) -> None:
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        self._set_hover(self._region_at(hwnd, x, y))
        event = _TRACKMOUSEEVENT(
            cbSize=ctypes.sizeof(_TRACKMOUSEEVENT),
            dwFlags=_TME_LEAVE,
            hwndTrack=hwnd,
        )
        _user32().TrackMouseEvent(ctypes.byref(event))

    def _region_at(
        self, hwnd: int, x: int, y: int
    ) -> Literal["usage", "menu"] | None:
        dpi = max(96, int(_user32().GetDpiForWindow(hwnd) or 96))
        bounds = _RECT()
        if not _user32().GetClientRect(hwnd, ctypes.byref(bounds)):
            return None
        from codex_usage_widget.taskbar_render import (  # noqa: PLC0415
            taskbar_hit_regions,
        )

        regions = taskbar_hit_regions(bounds.right, bounds.bottom, dpi)
        if _point_inside(x, y, regions.usage):
            return "usage"
        if _point_inside(x, y, regions.menu):
            return "menu"
        return None

    def _set_hover(self, region: Literal["usage", "menu"] | None) -> None:
        if region == self._hover_region:
            return
        self._hover_region = region
        with self._lock:
            hwnd = self._hwnd
        if hwnd:
            self._render_layered(hwnd)

    def _update_accessible_name(self, hwnd: int) -> None:
        with self._lock:
            model = self._model
        parts = [model.title, model.status_text]
        parts.extend(
            f"{row.label} {row.percent_text} 남음, {row.reset_text}"
            for row in model.rows
        )
        if model.error_text is not None:
            parts.append(model.error_text)
        _user32().SetWindowTextW(hwnd, ", ".join(parts))

    def _observe_taskbar(
        self, hwnd: int, stop_event: Event, generation: int
    ) -> None:
        _ = _user32().SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        while not stop_event.is_set():
            if not self._observe_once(hwnd, stop_event, generation):
                return
            if stop_event.wait(_TIMER_MS / 1000):
                return

    def _observe_once(self, hwnd: int, stop_event: Event, generation: int) -> bool:
        try:
            target = _find_target()
        except Exception:  # noqa: BLE001
            target = None
        if stop_event.is_set():
            return False
        with self._lock:
            if (
                stop_event.is_set()
                or generation != self._generation
                or stop_event is not self._stop_requested
                or hwnd != self._hwnd
            ):
                return False
            self._observed_target = target
        return bool(_user32().PostMessageW(hwnd, WM_APP_LAYOUT, 0, 0))

    def _apply_observed_target(self) -> None:
        with self._lock:
            hwnd = self._hwnd
            target = self._observed_target
        if not hwnd or target is None:
            with self._lock:
                self._attached = False
            if hwnd:
                _user32().ShowWindow(hwnd, SW_HIDE)
            return
        api = _Win32AttachmentApi()
        current_parent = api.get_parent(hwnd)
        attached = current_parent == target.parent
        if attached:
            try:
                api.position(hwnd, target.parent, target.placement, target.bounds)
            except OSError:
                attached = False
        else:
            attached = attach_transaction(
                api, hwnd, target.parent, target.placement, target.bounds
            )
        with self._lock:
            self._attached = attached
        if attached:
            self._render_layered(hwnd)
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        with self._lock:
            show = self._visible and self._attached
            hwnd = self._hwnd
        if hwnd:
            _user32().ShowWindow(hwnd, SW_SHOWNOACTIVATE if show else SW_HIDE)

    def _render_layered(self, hwnd: int) -> None:
        try:
            bounds = _RECT()
            if not _user32().GetClientRect(hwnd, ctypes.byref(bounds)):
                return
            with self._lock:
                model = self._model
            dpi = max(96, int(_user32().GetDpiForWindow(hwnd) or 96))
            from codex_usage_widget.taskbar_render import (  # noqa: PLC0415
                render_taskbar,
            )

            image = render_taskbar(
                model,
                dpi=dpi,
                width=bounds.right,
                height=bounds.bottom,
                hover_region=self._hover_region,
                light_theme=_system_uses_light_theme(),
                high_contrast=_high_contrast(),
            )
            update_layered_bitmap(hwnd, image)
        except Exception:  # noqa: BLE001
            with self._lock:
                self._attached = False
            _user32().ShowWindow(hwnd, SW_HIDE)


class _Win32AttachmentApi:
    def get_style(self, hwnd: int) -> int:
        _ = ctypes.set_last_error(0)
        value = _user32().GetWindowLongPtrW(hwnd, GWL_STYLE)
        if value == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        return int(value) & 0xFFFFFFFF

    def set_style(self, hwnd: int, style: int) -> None:
        _ = ctypes.set_last_error(0)
        result = _user32().SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        if result == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())

    def get_parent(self, hwnd: int) -> int:
        return int(_user32().GetParent(hwnd) or 0)

    def set_parent(self, hwnd: int, parent: int) -> None:
        _ = ctypes.set_last_error(0)
        result = _user32().SetParent(hwnd, parent or None)
        if not result and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())

    def position(self, hwnd: int, parent: int, rect: Rect, origin: Rect) -> None:
        del parent
        if not _user32().SetWindowPos(
            hwnd,
            None,
            rect.left - origin.left,
            rect.top - origin.top,
            rect.width,
            rect.height,
            SWP_NOACTIVATE | SWP_FRAMECHANGED,
        ):
            raise ctypes.WinError(ctypes.get_last_error())


def premultiplied_bgra(image: Image.Image) -> bytes:
    """Convert straight-alpha RGBA pixels for ``AC_SRC_ALPHA`` composition."""
    rgba = image.convert("RGBA")
    source = rgba.tobytes("raw", "RGBA")
    output = bytearray(len(source))
    for offset in range(0, len(source), 4):
        red, green, blue, alpha = source[offset : offset + 4]
        output[offset] = blue * alpha // 255
        output[offset + 1] = green * alpha // 255
        output[offset + 2] = red * alpha // 255
        output[offset + 3] = alpha
    return bytes(output)


def _point_inside(x: int, y: int, region: HitRegion) -> bool:
    return region.left <= x < region.right and region.top <= y < region.bottom


def update_layered_bitmap(hwnd: int, image: Image.Image) -> None:
    """Publish one per-pixel-alpha frame and release every temporary GDI handle."""
    width, height = image.size
    if width <= 0 or height <= 0:
        return
    user32 = _user32()
    gdi32 = _gdi32()
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise ctypes.WinError(ctypes.get_last_error())
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    if not memory_dc:
        _ = user32.ReleaseDC(None, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())
    bits = ctypes.c_void_p()
    info = _BITMAPINFO(
        bmiHeader=_BITMAPINFOHEADER(
            biSize=ctypes.sizeof(_BITMAPINFOHEADER),
            biWidth=width,
            biHeight=-height,
            biPlanes=1,
            biBitCount=32,
        )
    )
    bitmap = gdi32.CreateDIBSection(
        memory_dc,
        ctypes.byref(info),
        _DIB_RGB_COLORS,
        ctypes.byref(bits),
        None,
        0,
    )
    if not bitmap or not bits.value:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        _ = user32.ReleaseDC(None, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())
    old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
    try:
        pixels = premultiplied_bgra(image)
        _ = ctypes.memmove(bits, pixels, len(pixels))
        source = _POINT(0, 0)
        size = _SIZE(width, height)
        blend = _BLENDFUNCTION(0, 0, 255, _AC_SRC_ALPHA)
        if not user32.UpdateLayeredWindow(
            hwnd,
            screen_dc,
            None,
            ctypes.byref(size),
            memory_dc,
            ctypes.byref(source),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        gdi32.SelectObject(memory_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        _ = user32.ReleaseDC(None, screen_dc)


def _find_target() -> _Target | None:
    user32 = _user32()
    taskbar = int(user32.FindWindowW("Shell_TrayWnd", None) or 0)
    if not taskbar:
        return None
    bounds = _window_rect(taskbar)
    if bounds is None:
        return None
    notification = _find_descendant_rect(taskbar, {"TrayNotifyWnd", "ClockButton"})
    if notification is None:
        return None
    occupied_regions = _taskbar_occupied_regions(taskbar, bounds)
    task_buttons = tuple(
        region for class_name, region in occupied_regions
        if class_name == "Taskbar.TaskListButtonAutomationPeer"
    )
    if not task_buttons:
        return None
    interactive_before_notification = tuple(
        region
        for _, region in occupied_regions
        if region.left < notification.left
    )
    dpi = max(96, int(user32.GetDpiForWindow(taskbar) or 96))
    result = place_taskbar_widget(
        TaskbarGeometry(
            bounds,
            notification,
            _union_rects(interactive_before_notification),
            tuple(region for _, region in occupied_regions),
        ),
        dpi=dpi,
    )
    if result.rect is None:
        return None
    return _Target(taskbar, bounds, result.rect, dpi)


def _taskbar_occupied_regions(
    taskbar: int, taskbar_bounds: Rect
) -> tuple[tuple[str, Rect], ...]:
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [wintypes.LPVOID, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    initialized = int(ole32.CoInitializeEx(None, _COINIT_MULTITHREADED))
    should_uninitialize = initialized in (0, 1)
    if initialized < 0 and initialized != _RPC_E_CHANGED_MODE:
        return ()
    try:
        # comtypes otherwise defaults to apartment threading on first import,
        # conflicting with this dedicated MTA observer thread.
        setattr(sys, "coinit_flags", _COINIT_MULTITHREADED)  # noqa: B010
        import comtypes.client  # noqa: PLC0415

        _ = comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient  # noqa: PLC0415

        automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIAutomationClient.IUIAutomation,
        )
        root = automation.ElementFromHandle(taskbar)
        elements = root.FindAll(4, automation.CreateTrueCondition())
        found: list[tuple[str, Rect]] = []
        for index in range(elements.Length):
            element = elements.GetElement(index)
            native = element.CurrentBoundingRectangle
            rect = Rect(
                round(native.left),
                round(native.top),
                round(native.right),
                round(native.bottom),
            )
            if (
                element.CurrentControlType == _UIA_BUTTON_CONTROL_TYPE
                and rect.width > 0
                and rect.height > 0
                and _intersects(rect, taskbar_bounds)
            ):
                found.append((str(element.CurrentClassName), rect))
        if not found:
            return ()
        return tuple(found)
    # UI Automation providers execute outside this process and can fail with
    # COMError (which is not an OSError) during Explorer transitions.
    except Exception:  # noqa: BLE001
        return ()
    finally:
        if should_uninitialize:
            ole32.CoUninitialize()


def _union_rects(rects: tuple[Rect, ...]) -> Rect | None:
    if not rects:
        return None
    return Rect(
        min(rect.left for rect in rects),
        min(rect.top for rect in rects),
        max(rect.right for rect in rects),
        max(rect.bottom for rect in rects),
    )


def _find_descendant_rect(parent: int, classes: set[str]) -> Rect | None:
    user32 = _user32()
    found = ctypes.c_void_p()
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_type
    def visit(hwnd: int, _: int) -> bool:
        name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, name, len(name))
        if name.value in classes:
            found.value = hwnd
            return False
        return True

    user32.EnumChildWindows(parent, visit, 0)
    return _window_rect(int(found.value or 0)) if found.value else None


def _window_rect(hwnd: int) -> Rect | None:
    native = _RECT()
    if not hwnd or not _user32().GetWindowRect(hwnd, ctypes.byref(native)):
        return None
    return Rect(native.left, native.top, native.right, native.bottom)


def _intersects(first: Rect, second: Rect) -> bool:
    return (
        first.left < second.right
        and first.right > second.left
        and first.top < second.bottom
        and first.bottom > second.top
    )


def _system_uses_light_theme() -> bool:
    try:
        winreg = importlib.import_module("winreg")
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        finally:
            winreg.CloseKey(key)
        return bool(value)
    except (ImportError, OSError, AttributeError):
        return False


def _high_contrast() -> bool:
    value = _HIGHCONTRASTW(cbSize=ctypes.sizeof(_HIGHCONTRASTW))
    return bool(
        _user32().SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, value.cbSize, ctypes.byref(value), 0
        )
        and value.dwFlags & HCF_HIGHCONTRASTON
    )


def _user32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("user32", use_last_error=True)
    _configure_user32(library)
    return library


def _gdi32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("gdi32", use_last_error=True)
    library.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    library.DeleteObject.restype = wintypes.BOOL
    library.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    library.SelectObject.restype = wintypes.HGDIOBJ
    library.CreateCompatibleDC.argtypes = [wintypes.HDC]
    library.CreateCompatibleDC.restype = wintypes.HDC
    library.DeleteDC.argtypes = [wintypes.HDC]
    library.DeleteDC.restype = wintypes.BOOL
    library.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BITMAPINFO),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    library.CreateDIBSection.restype = wintypes.HBITMAP
    return library


def _configure_user32(library: ctypes.WinDLL) -> None:  # noqa: PLR0915
    library.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
    library.RegisterClassW.restype = wintypes.ATOM
    library.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    library.UnregisterClassW.restype = wintypes.BOOL
    library.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    library.CreateWindowExW.restype = wintypes.HWND
    library.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    library.DefWindowProcW.restype = LRESULT
    library.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    library.PostMessageW.restype = wintypes.BOOL
    library.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    library.GetMessageW.restype = wintypes.BOOL
    library.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    library.TranslateMessage.restype = wintypes.BOOL
    library.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    library.DispatchMessageW.restype = LRESULT
    library.UpdateLayeredWindow.argtypes = [
        wintypes.HWND,
        wintypes.HDC,
        ctypes.POINTER(_POINT),
        ctypes.POINTER(_SIZE),
        wintypes.HDC,
        ctypes.POINTER(_POINT),
        wintypes.COLORREF,
        ctypes.POINTER(_BLENDFUNCTION),
        wintypes.DWORD,
    ]
    library.UpdateLayeredWindow.restype = wintypes.BOOL
    library.GetDC.argtypes = [wintypes.HWND]
    library.GetDC.restype = wintypes.HDC
    library.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    library.ReleaseDC.restype = ctypes.c_int
    library.TrackMouseEvent.argtypes = [ctypes.POINTER(_TRACKMOUSEEVENT)]
    library.TrackMouseEvent.restype = wintypes.BOOL
    library.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PAINTSTRUCT)]
    library.BeginPaint.restype = wintypes.HDC
    library.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PAINTSTRUCT)]
    library.EndPaint.restype = wintypes.BOOL
    library.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    library.GetClientRect.restype = wintypes.BOOL
    library.InvalidateRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(_RECT),
        wintypes.BOOL,
    ]
    library.InvalidateRect.restype = wintypes.BOOL
    library.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    library.ShowWindow.restype = wintypes.BOOL
    library.DestroyWindow.argtypes = [wintypes.HWND]
    library.DestroyWindow.restype = wintypes.BOOL
    library.IsWindow.argtypes = [wintypes.HWND]
    library.IsWindow.restype = wintypes.BOOL
    library.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    library.SetWindowTextW.restype = wintypes.BOOL
    library.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    library.GetCursorPos.restype = wintypes.BOOL
    library.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    library.ScreenToClient.restype = wintypes.BOOL
    library.GetAsyncKeyState.argtypes = [ctypes.c_int]
    library.GetAsyncKeyState.restype = ctypes.c_short
    library.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    library.GetClassNameW.restype = ctypes.c_int
    library.EnumChildWindows.argtypes = [
        wintypes.HWND,
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    library.EnumChildWindows.restype = wintypes.BOOL
    library.SystemParametersInfoW.argtypes = [
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        wintypes.UINT,
    ]
    library.SystemParametersInfoW.restype = wintypes.BOOL
    library.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    library.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    library.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    library.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    library.GetParent.argtypes = [wintypes.HWND]
    library.GetParent.restype = wintypes.HWND
    library.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    library.SetParent.restype = wintypes.HWND
    library.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    library.SetWindowPos.restype = wintypes.BOOL
    library.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    library.FindWindowW.restype = wintypes.HWND
    library.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    library.GetWindowRect.restype = wintypes.BOOL
    library.GetDpiForWindow.argtypes = [wintypes.HWND]
    library.GetDpiForWindow.restype = wintypes.UINT
    library.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    library.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
