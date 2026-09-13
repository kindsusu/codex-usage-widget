from pathlib import Path

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

    def fail() -> int:
        raise RuntimeError

    monkeypatch.setattr("codex_usage_widget.runtime.run_widget", fail)
    monkeypatch.setattr(startup, "report_startup_problem", categories.append)

    assert app.main() == 1
    assert categories == ["startup_error"]
