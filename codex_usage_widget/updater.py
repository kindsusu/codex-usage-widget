# pyright: reportAny=false
"""Release-gated self-update: verify, gate, swap, and restart the install.

Only a published GitHub Release reaches users; a plain push to ``main`` never
does. Every attempt has to clear three independent gates before a single file
on disk changes -- the published sha256, ``py_compile`` over the whole staged
tree, and ``widget.pyw --selftest`` in a separate interpreter. Any failure
leaves the running installation untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, final

from codex_usage_widget import __version__

if TYPE_CHECKING:
    from collections.abc import Collection

UPDATE_REPO: Final = "kindsusu/codex-usage-widget"
_RELEASE_BASE: Final = f"https://github.com/{UPDATE_REPO}/releases"
ASSET_NAME: Final = "codex-usage-widget.zip"
LATEST_URL: Final = f"{_RELEASE_BASE}/latest"
ASSET_URL: Final = f"{_RELEASE_BASE}/latest/download/{ASSET_NAME}"
DIGEST_URL: Final = f"{ASSET_URL}.sha256"

FIRST_CHECK_MS: Final = 20_000
INTERVAL_MS: Final = 12 * 60 * 60 * 1000

#: Everything a release replaces wholesale. Nothing outside this tuple is read
#: from the archive, backed up, or written, so ``widget_config.json`` and the
#: user's ``.venv`` survive every update.
MANAGED_ENTRIES: Final = (
    "codex_usage_widget",
    "widget.pyw",
    "assets",
    "pyproject.toml",
    "실행.bat",
    "THIRD_PARTY_NOTICES.md",
)
STAGING_DIRNAME: Final = ".update-staging"
BACKUP_DIRNAME: Final = ".update-backup"
LOG_FILENAME: Final = "update.log"
INSTALL_ROOT: Final = Path(__file__).resolve().parent.parent

_USER_AGENT: Final = f"codex-usage-widget/{__version__}"
_TAG_TIMEOUT: Final = 10.0
_DIGEST_TIMEOUT: Final = 15.0
_ASSET_TIMEOUT: Final = 120.0
_GATE_TIMEOUT: Final = 180.0
_PIP_TIMEOUT: Final = 300.0
_TAG_MARKER: Final = "/tag/"
_NO_WINDOW: Final = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_NEW_GROUP: Final = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class UpdateGate(StrEnum):
    """The finite checks a release must clear before anything is installed."""

    DIGEST = "digest"
    COMPILE = "compile"
    SELFTEST = "selftest"
    DEPENDENCIES = "dependencies"


@final
class UpdateGateError(Exception):
    """A candidate release failed a gate, so nothing on disk was changed."""

    def __init__(self, gate: UpdateGate) -> None:
        """Record only the gate that rejected the release, never its content."""
        self.gate = gate
        super().__init__(f"release rejected at the {gate.value} gate")


@dataclass(frozen=True, slots=True)
class UpdatePaths:
    """Every filesystem location one update attempt is allowed to touch."""

    root: Path
    staging: Path
    backup: Path
    log: Path


@dataclass(frozen=True, slots=True)
class MoveStep:
    """One rename in a backup, install, or rollback plan."""

    source: Path
    destination: Path


class _Fetch(Protocol):
    def __call__(self, url: str, timeout: float) -> tuple[bytes, str]: ...


@dataclass(frozen=True, slots=True)
class ReleaseSource:
    """Network boundary: the three fixed URLs plus the transport to read them."""

    latest_url: str
    asset_url: str
    digest_url: str
    fetch: _Fetch


def default_source() -> ReleaseSource:
    """Bind the fixed repository URLs to the plain HTTPS transport."""
    return ReleaseSource(
        latest_url=LATEST_URL,
        asset_url=ASSET_URL,
        digest_url=DIGEST_URL,
        fetch=_http_get,
    )


def plan_paths(root: Path) -> UpdatePaths:
    """Derive the staging, backup, and log locations beside an installation."""
    return UpdatePaths(
        root=root,
        staging=root / STAGING_DIRNAME,
        backup=root / BACKUP_DIRNAME,
        log=root / LOG_FILENAME,
    )


def parse_version(tag: str) -> tuple[int, ...] | None:
    """Parse ``v0.3.0`` into a comparable tuple, or ``None`` when not numeric."""
    cleaned = tag.strip().lstrip("vV")
    parts = cleaned.split(".")
    if not cleaned or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(latest: str, current: str) -> bool:
    """Report whether a release tag is strictly newer than the running version.

    Anything unparsable on either side answers ``False``: an unreadable tag must
    never be treated as an upgrade.
    """
    new, running = parse_version(latest), parse_version(current)
    if new is None or running is None:
        return False
    width = max(len(new), len(running))
    return _padded(new, width) > _padded(running, width)


def expected_digest(digest_text: str) -> str:
    """Read the hex digest out of a ``sha256sum`` style file body."""
    parts = digest_text.split()
    return parts[0].strip().lower() if parts else ""


def digest_matches(payload: bytes, digest_text: str) -> bool:
    """Report whether payload hashes to the digest published with a release."""
    expected = expected_digest(digest_text)
    if len(expected) != len(hashlib.sha256().hexdigest()):
        return False
    return hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected)


def is_managed_member(name: str) -> bool:
    """Report whether an archive entry belongs to the replaceable install set.

    Rejects absolute, drive-qualified, and parent-relative names so a crafted
    archive cannot write outside the staging directory.
    """
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized:
        return False
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments[:-1]):
        return False
    return segments[0] in MANAGED_ENTRIES


def plan_backup(paths: UpdatePaths, existing: Collection[str]) -> tuple[MoveStep, ...]:
    """Plan moving every installed managed entry aside, in declaration order."""
    return tuple(
        MoveStep(paths.root / name, paths.backup / name)
        for name in MANAGED_ENTRIES
        if name in existing
    )


def plan_install(paths: UpdatePaths, staged: Collection[str]) -> tuple[MoveStep, ...]:
    """Plan moving every staged managed entry into the installation root."""
    return tuple(
        MoveStep(paths.staging / name, paths.root / name)
        for name in MANAGED_ENTRIES
        if name in staged
    )


def plan_rollback(backup: Collection[MoveStep]) -> tuple[MoveStep, ...]:
    """Reverse a completed backup plan so the previous installation returns."""
    return tuple(
        MoveStep(step.destination, step.source) for step in reversed(list(backup))
    )


def append_log(paths: UpdatePaths, message: str) -> None:
    """Append one timestamped line to ``update.log``.

    Callers pass finite categories and release tags only -- never a path, a
    token, or a raw exception message -- so the file stays safe to share.
    """
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with suppress(OSError), paths.log.open("a", encoding="utf-8") as log:
        _ = log.write(f"{stamp} [update] {message}\n")


def fetch_latest_tag(source: ReleaseSource) -> str:
    """Resolve the newest published tag from the release redirect target.

    Reading github.com's redirect instead of api.github.com keeps the check off
    the rate-limited API.
    """
    _, final_url = source.fetch(source.latest_url, _TAG_TIMEOUT)
    if _TAG_MARKER not in final_url:
        return ""
    return final_url.rstrip("/").rsplit(_TAG_MARKER, 1)[-1]


def download_release(source: ReleaseSource) -> bytes:
    """Download the release archive and prove it matches its published digest."""
    archive, _ = source.fetch(source.asset_url, _ASSET_TIMEOUT)
    digest, _ = source.fetch(source.digest_url, _DIGEST_TIMEOUT)
    if not digest_matches(archive, digest.decode("utf-8", "replace")):
        raise UpdateGateError(UpdateGate.DIGEST)
    return archive


def stage_archive(paths: UpdatePaths, archive: bytes) -> tuple[str, ...]:
    """Extract the managed entries of a release into a clean staging tree."""
    _reset_directory(paths.staging)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = [name for name in bundle.namelist() if is_managed_member(name)]
        bundle.extractall(paths.staging, members=members)
    present = {name.replace("\\", "/").split("/")[0] for name in members}
    return tuple(name for name in MANAGED_ENTRIES if name in present)


def run_gate(paths: UpdatePaths) -> None:
    """Compile every staged source, then self-test it in a fresh interpreter."""
    sources = [*sorted(paths.staging.rglob("*.py")), paths.staging / "widget.pyw"]
    with tempfile.TemporaryDirectory() as cache:
        discard = str(Path(cache) / "gate.pyc")
        for source in sources:
            try:
                _ = py_compile.compile(str(source), cfile=discard, doraise=True)
            except (py_compile.PyCompileError, OSError, ValueError) as error:
                raise UpdateGateError(UpdateGate.COMPILE) from error
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(paths.staging)
    completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell, staged tree
        [_interpreter(paths.root), str(paths.staging / "widget.pyw"), "--selftest"],
        cwd=str(paths.staging),
        env=environment,
        timeout=_GATE_TIMEOUT,
        check=False,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if completed.returncode != 0:
        raise UpdateGateError(UpdateGate.SELFTEST)


def install_staged(paths: UpdatePaths, staged: Collection[str]) -> None:
    """Back up the current install, move the staged release in, refresh deps.

    Any failure after the backup restores it, so the widget keeps running on
    the files it started with.
    """
    existing = {name for name in MANAGED_ENTRIES if (paths.root / name).exists()}
    backup = plan_backup(paths, existing)
    install = plan_install(paths, staged)
    _reset_directory(paths.backup)
    _apply_moves(backup)
    try:
        _apply_moves(install)
        _install_dependencies(paths.root)
    except (OSError, UpdateGateError):
        _apply_moves(plan_rollback(backup))
        append_log(paths, "install failed - restored the previous files")
        raise
    _remove(paths.staging)


def relaunch(root: Path) -> None:
    """Start a replacement widget process from the freshly installed files."""
    launcher = root / ".venv" / "Scripts" / "pythonw.exe"
    fallback = Path(sys.executable).with_name("pythonw.exe")
    if launcher.exists():
        interpreter = str(launcher)
    else:
        interpreter = str(fallback) if fallback.exists() else sys.executable
    _ = subprocess.Popen(  # noqa: S603 -- fixed argv, no shell, own entry point
        [interpreter, str(root / "widget.pyw")],
        cwd=str(root),
        creationflags=_NEW_GROUP,
    )


def try_update(
    current_version: str = __version__,
    *,
    root: Path = INSTALL_ROOT,
    source: ReleaseSource | None = None,
) -> str | None:
    """Run one complete update attempt without ever raising.

    Returns the installed tag when the widget must restart into it, and ``None``
    when there was nothing to do or an attempt was stopped by a gate.
    """
    paths = plan_paths(root)
    release = default_source() if source is None else source
    try:
        return _update(release, paths, current_version)
    except UpdateGateError as error:
        append_log(paths, f"stopped: {error}")
    except Exception as error:  # noqa: BLE001 -- category only, message may hold paths
        append_log(paths, f"stopped: {type(error).__name__}")
    return None


def _update(
    source: ReleaseSource,
    paths: UpdatePaths,
    current_version: str,
) -> str | None:
    tag = fetch_latest_tag(source)
    if not is_newer(tag, current_version):
        return None
    append_log(paths, f"found {tag} (running v{current_version}) - downloading")
    staged = stage_archive(paths, download_release(source))
    run_gate(paths)
    append_log(paths, f"{tag} passed the digest, compile, and selftest gates")
    install_staged(paths, staged)
    append_log(paths, f"{tag} installed - restarting")
    return tag


def _padded(version: tuple[int, ...], width: int) -> tuple[int, ...]:
    return version + (0,) * (width - len(version))


def _http_get(url: str, timeout: float) -> tuple[bytes, str]:
    request = urllib.request.Request(  # noqa: S310 -- fixed https release URLs
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read(), response.geturl()


def _interpreter(root: Path) -> str:
    """Prefer the installation's own virtual environment over the running one."""
    candidate = root / ".venv" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else sys.executable


def _install_dependencies(root: Path) -> None:
    """Re-run the editable install so a release's new requirements land."""
    completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        [_interpreter(root), "-m", "pip", "install", "-e", str(root), "--quiet"],
        cwd=str(root),
        timeout=_PIP_TIMEOUT,
        check=False,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if completed.returncode != 0:
        raise UpdateGateError(UpdateGate.DEPENDENCIES)


def _apply_moves(steps: Collection[MoveStep]) -> None:
    for step in steps:
        step.destination.parent.mkdir(parents=True, exist_ok=True)
        _remove(step.destination)
        _ = shutil.move(str(step.source), str(step.destination))


def _reset_directory(path: Path) -> None:
    _remove(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)
