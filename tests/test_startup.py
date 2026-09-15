from pathlib import Path
from typing import Literal

import pytest

import codex_usage_widget.app as app
import codex_usage_widget.startup as startup


def test_startup_diagnostic_contains_only_timestamp_and_finite_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ignore_message(_message: str) -> None:
        return None

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(startup, "_show_message", ignore_message)

    startup.report_startup_problem("secret raw exception payload")

    text = (tmp_path / "CodexUsageWidget" / "startup.log").read_text(encoding="utf-8")
    assert text.endswith(" startup_error\n")
    assert "secret" not in text


def test_app_boundary_reports_unexpected_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    categories: list[str] = []
    lifecycle: list[tuple[str, type[BaseException] | None]] = []

    def fail() -> int:
        raise RuntimeError

    def record_lifecycle(
        event: startup.LifecycleEvent | Literal["fatal"],
        error_type: type[BaseException] | None = None,
    ) -> None:
        lifecycle.append((event, error_type))

    monkeypatch.setattr("codex_usage_widget.runtime.run_widget", fail)
    monkeypatch.setattr(startup, "report_startup_problem", categories.append)
    monkeypatch.setattr(
        startup,
        "report_lifecycle_event",
        record_lifecycle,
    )

    assert app.main() == 1
    assert categories == ["startup_error"]
    assert lifecycle == [("fatal", RuntimeError)]


def test_lifecycle_diagnostic_is_bounded_and_omits_exception_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = tmp_path / "CodexUsageWidget" / "lifecycle.log"
    path.parent.mkdir(parents=True)
    _ = path.write_bytes(b"old record\n" * 10_000)

    error = RuntimeError("secret raw exception payload")
    startup.report_lifecycle_event("fatal", type(error))

    raw = path.read_bytes()
    assert len(raw) <= 64 * 1024
    assert raw.endswith(b" fatal:RuntimeError\n")
    assert b"secret" not in raw
