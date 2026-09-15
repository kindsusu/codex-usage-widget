"""Start the widget outside the caller's process tree on Windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from codex_usage_widget.startup import report_startup_problem

_NO_WINDOW: Final = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED_PROCESS: Final = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
_NEW_GROUP: Final = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_BREAKAWAY: Final = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
_WMI_TIMEOUT_SECONDS: Final = 15.0
_WMI_SCRIPT: Final = """
$startup = New-CimInstance -ClassName Win32_ProcessStartup -Property @{
    ShowWindow = 0
} -ClientOnly
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $env:CODEX_WIDGET_LAUNCH_COMMAND
    CurrentDirectory = $env:CODEX_WIDGET_LAUNCH_DIRECTORY
    ProcessStartupInformation = $startup
}
if ($null -eq $result) { exit 1 }
exit [int]$result.ReturnValue
"""


class DetachedLaunchError(RuntimeError):
    """Neither independent Windows launch mechanism could create the widget."""


class _WmiLaunchError(subprocess.SubprocessError):
    """WMI was reachable but refused to create the requested process."""


def widget_command(root: Path) -> tuple[str, str]:
    """Return the preferred GUI interpreter and widget entry point."""
    virtual = root / ".venv" / "Scripts" / "pythonw.exe"
    sibling = Path(sys.executable).with_name("pythonw.exe")
    if virtual.exists():
        interpreter = virtual
    elif sibling.exists():
        interpreter = sibling
    else:
        interpreter = Path(sys.executable)
    return str(interpreter), str(root / "widget.pyw")


def launch_detached(root: Path) -> None:
    """Create a widget that survives termination of the launching process tree.

    Codex and other process hosts can put every descendant in a kill-on-close
    Windows Job. WMI creates the widget from the system's provider process, so
    it does not inherit that Job. A direct breakaway launch covers machines
    where WMI is unavailable but the caller's Job permits explicit breakaway.
    """
    launch_command_detached(widget_command(root), root)


def launch_command_detached(command: tuple[str, ...], cwd: Path) -> None:
    """Create any fixed command through the same independent process boundary.

    This narrower primitive also lets diagnostics exercise process survival
    with a short-lived benign child instead of restarting the real widget.
    """
    if os.name != "nt":
        _ = subprocess.Popen(  # noqa: S603 -- fixed local entry point
            command,
            cwd=str(cwd),
            start_new_session=True,
        )
        return

    try:
        _launch_via_wmi(command, cwd)
    except (OSError, subprocess.SubprocessError):
        pass
    else:
        return

    try:
        _ = subprocess.Popen(  # noqa: S603 -- fixed local entry point
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=_BREAKAWAY | _DETACHED_PROCESS | _NEW_GROUP,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DetachedLaunchError from error


def _launch_via_wmi(command: tuple[str, ...], cwd: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        raise FileNotFoundError
    environment = dict(os.environ)
    environment["CODEX_WIDGET_LAUNCH_COMMAND"] = subprocess.list2cmdline(command)
    environment["CODEX_WIDGET_LAUNCH_DIRECTORY"] = str(cwd)
    completed = subprocess.run(  # noqa: S603 -- fixed PowerShell program and script
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _WMI_SCRIPT,
        ],
        env=environment,
        timeout=_WMI_TIMEOUT_SECONDS,
        check=False,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if completed.returncode != 0:
        raise _WmiLaunchError


def main(argv: list[str] | None = None) -> int:
    """Launch from ``실행.bat`` and report a visible finite error on failure."""
    arguments = sys.argv[1:] if argv is None else argv
    root = Path(arguments[0]).resolve() if arguments else Path.cwd()
    try:
        launch_detached(root)
    except DetachedLaunchError:
        report_startup_problem("launch_error")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
