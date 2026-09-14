import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from codex_usage_widget import updater
from codex_usage_widget.updater import (
    MANAGED_ENTRIES,
    MoveStep,
    ReleaseSource,
    UpdatePaths,
    UpdateGate,
    UpdateGateError,
    digest_matches,
    download_release,
    expected_digest,
    fetch_latest_tag,
    is_managed_member,
    is_newer,
    parse_version,
    plan_backup,
    plan_install,
    plan_paths,
    plan_rollback,
    stage_archive,
)

ARCHIVE_FILES = {
    "codex_usage_widget/__init__.py": b'__version__ = "9.9.9"\n',
    "widget.pyw": b"raise SystemExit(0)\n",
    "assets/icon/codex.png": b"png",
    "pyproject.toml": b"[project]\n",
}


def _fake_source(
    responses: dict[str, tuple[bytes, str]],
    calls: list[str] | None = None,
) -> ReleaseSource:
    def fetch(url: str, timeout: float) -> tuple[bytes, str]:
        assert timeout > 0
        if calls is not None:
            calls.append(url)
        return responses[url]

    return ReleaseSource(
        latest_url="latest",
        asset_url="asset",
        digest_url="digest",
        fetch=fetch,
    )


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, payload in files.items():
            bundle.writestr(name, payload)
    return buffer.getvalue()


def _digest_line(payload: bytes) -> bytes:
    return f"{hashlib.sha256(payload).hexdigest()}  release.zip\n".encode()


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.3.0", (0, 3, 0)),
        ("0.3.0", (0, 3, 0)),
        ("  V1.2  ", (1, 2)),
        ("v", None),
        ("", None),
        ("latest", None),
        ("v1.2.0-rc1", None),
    ],
)
def test_parse_version_accepts_only_numeric_tags(
    tag: str,
    expected: tuple[int, ...] | None,
) -> None:
    # Given / When / Then
    assert parse_version(tag) == expected


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.3.1", "0.3.0", True),
        ("v0.4.0", "0.3.9", True),
        ("v1.0", "0.9.9", True),
        ("v0.3.0", "0.3.0", False),
        ("v0.3", "0.3.0", False),
        ("v0.2.9", "0.3.0", False),
        ("latest", "0.3.0", False),
        ("v0.4.0", "nightly", False),
    ],
)
def test_is_newer_upgrades_only_on_a_strictly_greater_tag(
    latest: str,
    current: str,
    expected: bool,
) -> None:
    # Given / When / Then
    assert is_newer(latest, current) is expected


def test_expected_digest_reads_the_sha256sum_layout() -> None:
    # Given
    body = "ABCDEF0123  codex-usage-widget.zip\n"

    # When / Then
    assert expected_digest(body) == "abcdef0123"
    assert expected_digest("   ") == ""


def test_digest_matches_only_for_untampered_payloads() -> None:
    # Given
    payload = b"release-archive"
    published = _digest_line(payload).decode()

    # When / Then
    assert digest_matches(payload, published) is True
    assert digest_matches(b"tampered", published) is False
    assert digest_matches(payload, "not-a-digest") is False
    assert digest_matches(payload, "") is False


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("widget.pyw", True),
        ("codex_usage_widget/config.py", True),
        ("assets/pets/image-1.png", True),
        ("실행.bat", True),
        ("widget_config.json", False),
        (".venv/Scripts/python.exe", False),
        ("../evil.py", False),
        ("codex_usage_widget/../../evil.py", False),
        ("/etc/passwd", False),
        ("C:/Windows/system32/evil.dll", False),
        ("", False),
    ],
)
def test_is_managed_member_rejects_anything_outside_the_release_set(
    member: str,
    expected: bool,
) -> None:
    # Given / When / Then
    assert is_managed_member(member) is expected


def test_plan_paths_keeps_every_scratch_location_beside_the_install() -> None:
    # Given
    root = Path("C:/widget")

    # When
    paths = plan_paths(root)

    # Then
    assert paths == UpdatePaths(
        root=root,
        staging=root / ".update-staging",
        backup=root / ".update-backup",
        log=root / "update.log",
    )


def test_plan_backup_moves_only_installed_entries_in_declaration_order() -> None:
    # Given
    paths = plan_paths(Path("C:/widget"))

    # When
    steps = plan_backup(
        paths,
        {"widget.pyw", "codex_usage_widget", "widget_config.json"},
    )

    # Then
    assert steps == (
        MoveStep(
            paths.root / "codex_usage_widget",
            paths.backup / "codex_usage_widget",
        ),
        MoveStep(paths.root / "widget.pyw", paths.backup / "widget.pyw"),
    )


def test_plan_install_moves_only_entries_the_release_actually_shipped() -> None:
    # Given
    paths = plan_paths(Path("C:/widget"))

    # When
    steps = plan_install(paths, {"assets", "widget.pyw"})

    # Then
    assert steps == (
        MoveStep(paths.staging / "widget.pyw", paths.root / "widget.pyw"),
        MoveStep(paths.staging / "assets", paths.root / "assets"),
    )


def test_plan_rollback_reverses_the_backup_plan_last_move_first() -> None:
    # Given
    paths = plan_paths(Path("C:/widget"))
    backup = plan_backup(paths, set(MANAGED_ENTRIES))

    # When
    rollback = plan_rollback(backup)

    # Then
    assert rollback == tuple(
        MoveStep(step.destination, step.source) for step in reversed(backup)
    )
    assert rollback[0].source == paths.backup / MANAGED_ENTRIES[-1]
    assert rollback[0].destination == paths.root / MANAGED_ENTRIES[-1]


def test_fetch_latest_tag_reads_the_release_redirect_target() -> None:
    # Given
    source = _fake_source(
        {"latest": (b"", "https://github.com/o/r/releases/tag/v0.4.0")},
    )

    # When / Then
    assert fetch_latest_tag(source) == "v0.4.0"


def test_fetch_latest_tag_is_empty_when_no_release_was_published() -> None:
    # Given
    source = _fake_source({"latest": (b"", "https://github.com/o/r/releases")})

    # When / Then
    assert fetch_latest_tag(source) == ""


def test_download_release_returns_bytes_that_match_the_published_digest() -> None:
    # Given
    archive = _zip_bytes(ARCHIVE_FILES)
    source = _fake_source(
        {"asset": (archive, "asset"), "digest": (_digest_line(archive), "digest")},
    )

    # When / Then
    assert download_release(source) == archive


def test_download_release_refuses_a_payload_the_digest_does_not_cover() -> None:
    # Given
    archive = _zip_bytes(ARCHIVE_FILES)
    source = _fake_source(
        {"asset": (archive, "asset"), "digest": (_digest_line(b"other"), "digest")},
    )

    # When / Then
    with pytest.raises(UpdateGateError) as failure:
        _ = download_release(source)
    assert failure.value.gate is UpdateGate.DIGEST


def test_stage_archive_extracts_managed_entries_and_drops_the_rest(
    tmp_path: Path,
) -> None:
    # Given
    paths = plan_paths(tmp_path)
    archive = _zip_bytes({**ARCHIVE_FILES, "widget_config.json": b"{}", "evil.py": b""})

    # When
    staged = stage_archive(paths, archive)

    # Then
    assert staged == ("codex_usage_widget", "widget.pyw", "assets", "pyproject.toml")
    assert (paths.staging / "codex_usage_widget" / "__init__.py").exists()
    assert not (paths.staging / "widget_config.json").exists()
    assert not (paths.staging / "evil.py").exists()


def test_stage_archive_clears_a_leftover_staging_tree_first(tmp_path: Path) -> None:
    # Given
    paths = plan_paths(tmp_path)
    (paths.staging / "codex_usage_widget").mkdir(parents=True)
    stale = paths.staging / "codex_usage_widget" / "removed_module.py"
    _ = stale.write_text("stale", encoding="utf-8")

    # When
    _ = stage_archive(paths, _zip_bytes(ARCHIVE_FILES))

    # Then
    assert not stale.exists()
    assert (paths.staging / "widget.pyw").exists()


def test_append_log_records_a_timestamped_line_without_paths(tmp_path: Path) -> None:
    # Given
    paths = plan_paths(tmp_path)

    # When
    updater.append_log(paths, "found v0.4.0 - downloading")
    updater.append_log(paths, "stopped: release digest mismatch")

    # Then
    lines = paths.log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("[update] found v0.4.0 - downloading")
    assert str(tmp_path) not in paths.log.read_text(encoding="utf-8")


def test_try_update_reports_nothing_to_do_when_the_release_is_not_newer(
    tmp_path: Path,
) -> None:
    # Given
    calls: list[str] = []
    source = _fake_source(
        {"latest": (b"", "https://github.com/o/r/releases/tag/v0.1.0")},
        calls,
    )

    # When
    tag = updater.try_update("0.3.0", root=tmp_path, source=source)

    # Then
    assert tag is None
    assert calls == ["latest"]
    assert not plan_paths(tmp_path).log.exists()


def test_try_update_stops_and_logs_when_the_digest_does_not_match(
    tmp_path: Path,
) -> None:
    # Given
    archive = _zip_bytes(ARCHIVE_FILES)
    source = _fake_source(
        {
            "latest": (b"", "https://github.com/o/r/releases/tag/v9.9.9"),
            "asset": (archive, "asset"),
            "digest": (_digest_line(b"tampered"), "digest"),
        },
    )

    # When
    tag = updater.try_update("0.3.0", root=tmp_path, source=source)

    # Then
    assert tag is None
    log = plan_paths(tmp_path).log.read_text(encoding="utf-8")
    assert "rejected at the digest gate" in log
    assert not (tmp_path / "widget.pyw").exists()


def _install_fixture(tmp_path: Path) -> tuple[UpdatePaths, tuple[str, ...]]:
    paths = plan_paths(tmp_path)
    package = tmp_path / "codex_usage_widget"
    package.mkdir()
    _ = (package / "__init__.py").write_text(
        '__version__ = "0.3.0"\n',
        encoding="utf-8",
    )
    _ = (tmp_path / "widget.pyw").write_text("old entry point\n", encoding="utf-8")
    _ = (tmp_path / "widget_config.json").write_text("{}", encoding="utf-8")
    return paths, stage_archive(paths, _zip_bytes(ARCHIVE_FILES))


def test_install_staged_replaces_managed_entries_and_keeps_user_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    paths, staged = _install_fixture(tmp_path)

    def succeed(_root: Path) -> None:
        return None

    monkeypatch.setattr(updater, "_install_dependencies", succeed)

    # When
    updater.install_staged(paths, staged)

    # Then
    assert (tmp_path / "widget.pyw").read_bytes() == ARCHIVE_FILES["widget.pyw"]
    assert (tmp_path / "codex_usage_widget" / "__init__.py").read_text(
        encoding="utf-8",
    ) == '__version__ = "9.9.9"\n'
    assert (tmp_path / "widget_config.json").exists()
    backed_up = (paths.backup / "widget.pyw").read_text(encoding="utf-8")
    assert backed_up == "old entry point\n"
    assert not paths.staging.exists()


def test_install_staged_restores_the_backup_when_dependencies_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    paths, staged = _install_fixture(tmp_path)

    def refuse(_root: Path) -> None:
        raise UpdateGateError(UpdateGate.DEPENDENCIES)

    monkeypatch.setattr(updater, "_install_dependencies", refuse)

    # When
    with pytest.raises(UpdateGateError) as failure:
        updater.install_staged(paths, staged)

    # Then
    assert failure.value.gate is UpdateGate.DEPENDENCIES
    assert (tmp_path / "widget.pyw").read_text(encoding="utf-8") == "old entry point\n"
    assert (tmp_path / "codex_usage_widget" / "__init__.py").read_text(
        encoding="utf-8",
    ) == '__version__ = "0.3.0"\n'
    assert (tmp_path / "widget_config.json").exists()
    assert "restored the previous files" in paths.log.read_text(encoding="utf-8")
