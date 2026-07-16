"""Discover ordered local Codex executable candidates."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def discover_codex_executables() -> tuple[Path, ...]:
    """Return an explicit override or automatic PATH and desktop candidates."""
    configured = os.environ.get("CODEX_EXE")
    if configured:
        candidate = Path(configured).expanduser()
        return (candidate.resolve(),) if candidate.is_file() else ()

    candidates: list[Path] = []
    deferred: list[Path] = []
    if found := shutil.which("codex"):
        path_candidate = Path(found).resolve()
        target = (
            deferred
            if any(part.casefold() == "windowsapps" for part in path_candidate.parts)
            else candidates
        )
        target.append(path_candidate)

    if local_app_data := os.environ.get("LOCALAPPDATA"):
        install_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
        installed = sorted(install_root.glob("*/codex.exe"), reverse=True)
        candidates.extend(path.resolve() for path in installed if path.is_file())
    candidates.extend(deferred)
    return tuple(dict.fromkeys(candidates))
