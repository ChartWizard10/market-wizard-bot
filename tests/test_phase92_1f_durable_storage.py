"""Phase 92-1F — durable commercial-evidence storage acceptance tests."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src import signal_outcome_ledger as ledger
from src import signal_outcome_storage as storage


def _cfg(tmp_path: Path, enabled: bool = True) -> dict:
    return {
        "scan": {"timezone": "America/New_York"},
        "state": {"state_file": str(tmp_path / "alert_history.json")},
        "research_archive": {"directory": str(tmp_path / "research_archive")},
        "signal_outcomes": {"enabled": enabled, "directory": str(tmp_path / "signal_outcomes")},
    }


def test_storage_jurisdiction_is_separate_and_read_only_health_does_not_create(tmp_path):
    cfg = _cfg(tmp_path)
    before = set(tmp_path.iterdir())
    health = storage.storage_health(cfg)
    assert health["enabled"] is True
    assert health["path_collision"] is False
    assert health["exists"] is False
    assert health["mount_alignment"] == "UNVERIFIED"
    assert set(tmp_path.iterdir()) == before


def test_railway_volume_mount_alignment_is_explicit_not_inferred(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    assert storage.mount_alignment(cfg) == "UNVERIFIED"

    mount = tmp_path / "volume"
    mount.mkdir()
    cfg["signal_outcomes"]["directory"] = str(mount / ".state" / "signal_outcomes")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(mount))
    assert storage.mount_alignment(cfg) == "ALIGNED"

    cfg["signal_outcomes"]["directory"] = str(tmp_path / "outside" / "signal_outcomes")
    assert storage.mount_alignment(cfg) == "MISALIGNED"


def test_probe_is_append_only_and_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    first = storage.append_probe(cfg, "pre-restart-001", note="before restart")
    second = storage.append_probe(cfg, "pre-restart-001", note="must not replace")
    assert first["status"] == "appended"
    assert second["status"] == "duplicate_ignored"
    lines = Path(first["path"]).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["probe_id"] == "pre-restart-001"
    assert row["note"] == "before restart"


def test_probe_survives_fresh_python_process_read(tmp_path):
    cfg = _cfg(tmp_path)
    written = storage.append_probe(cfg, "restart-001")
    assert written["ok"] is True
    code = (
        "import json,sys; "
        "from src import signal_outcome_storage as s; "
        "cfg=json.loads(sys.argv[1]); "
        "print(json.dumps(s.verify_probe(cfg, sys.argv[2]), sort_keys=True))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, json.dumps(cfg), "restart-001"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["status"] == "PRESENT"
    assert result["match_count"] == 1


def test_reloading_storage_module_does_not_change_probe(tmp_path):
    cfg = _cfg(tmp_path)
    storage.append_probe(cfg, "reload-001")
    importlib.reload(storage)
    result = storage.verify_probe(cfg, "reload-001")
    assert result["ok"] is True
    assert result["match_count"] == 1


def test_malformed_probe_line_isolated_and_reported(tmp_path):
    cfg = _cfg(tmp_path)
    written = storage.append_probe(cfg, "valid-001")
    path = Path(written["path"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("NOT_JSON\n")
        handle.write(json.dumps({"schema_version": "wrong", "probe_id": "bad"}) + "\n")
    view = storage.read_probes(cfg)
    assert len(view["probes"]) == 1
    assert view["probes"][0]["probe_id"] == "valid-001"
    assert view["stats"]["malformed_lines"] == 2


def test_duplicate_probe_ids_are_detected_without_rewriting(tmp_path):
    cfg = _cfg(tmp_path)
    written = storage.append_probe(cfg, "dup-001")
    path = Path(written["path"])
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    view = storage.read_probes(cfg)
    assert view["stats"]["duplicate_probe_ids"] == ["dup-001"]
    assert len(view["probes"]) == 2


def test_path_collision_fails_closed(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["signal_outcomes"]["directory"] = cfg["research_archive"]["directory"]
    result = storage.append_probe(cfg, "collision-001")
    assert result["ok"] is False
    assert result["status"] == "path_collision"


def test_disabled_store_does_not_write_probe(tmp_path):
    cfg = _cfg(tmp_path, enabled=False)
    result = storage.append_probe(cfg, "disabled-001")
    assert result["ok"] is True
    assert result["status"] == "disabled"
    assert not ledger.ledger_dir(cfg).exists()


def test_probe_verification_requires_exact_anchor(tmp_path):
    cfg = _cfg(tmp_path)
    storage.append_probe(cfg, "exact-001")
    assert storage.verify_probe(cfg, "exact-001")["status"] == "PRESENT"
    assert storage.verify_probe(cfg, "exact-002")["status"] == "MISSING"


def test_probe_does_not_touch_event_or_outcome_partitions(tmp_path):
    cfg = _cfg(tmp_path)
    result = storage.append_probe(cfg, "isolation-001")
    assert result["ok"] is True
    assert not ledger.events_dir(cfg).exists()
    assert not ledger.outcomes_dir(cfg).exists()


def test_storage_health_reports_probe_and_mount_state(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    mount = tmp_path / "volume"
    mount.mkdir()
    cfg["signal_outcomes"]["directory"] = str(mount / ".state" / "signal_outcomes")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(mount))
    monkeypatch.setenv("RAILWAY_VOLUME_NAME", "mw-production")
    storage.append_probe(cfg, "health-001")
    health = storage.storage_health(cfg)
    assert health["exists"] is True
    assert health["directory"] is True
    assert health["probe_count"] == 1
    assert health["mount_alignment"] == "ALIGNED"
    assert health["railway_volume_name"] == "mw-production"
    assert health["path_collision"] is False


def test_no_retention_pruning_or_replacement_exists_in_phase_1f_storage():
    source = Path("src/signal_outcome_storage.py").read_text(encoding="utf-8")
    assert "retention_days" not in source
    assert "unlink(" not in source
    assert "replace(" not in source
    assert "truncate" not in source.lower()


def test_storage_module_is_not_on_critical_scan_path():
    scheduler = Path("src/scheduler.py").read_text(encoding="utf-8")
    main = Path("main.py").read_text(encoding="utf-8")
    assert "signal_outcome_storage" not in scheduler
    assert "signal_outcome_storage" not in main


def test_storage_verification_has_zero_strategy_authority_contract():
    source = Path("src/signal_outcome_storage.py").read_text(encoding="utf-8")
    for forbidden in (
        "final_tier", "capital_action", "raw_score", "candidate_cap",
        "cooldown", "dedup", "routing", "claude_client", "anthropic",
    ):
        assert forbidden not in source


def test_probe_fingerprint_is_deterministic_and_nonempty(tmp_path):
    cfg = _cfg(tmp_path)
    result = storage.append_probe(cfg, "fingerprint-001")
    row = json.loads(Path(result["path"]).read_text(encoding="utf-8").splitlines()[0])
    assert len(row["probe_sha256"]) == 64
    assert row["probe_sha256"] == storage._probe_fingerprint({k: v for k, v in row.items() if k != "probe_sha256"})


def test_bad_probe_id_fails_closed(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(ValueError):
        storage.append_probe(cfg, "bad probe")


def test_corrupt_event_ledger_remains_readable_through_storage_health(tmp_path):
    cfg = _cfg(tmp_path)
    event_path = ledger.events_dir(cfg) / "2026-09-12.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text("NOT_JSON\n", encoding="utf-8")
    health = storage.storage_health(cfg)
    assert health["path_collision"] is False
    events = ledger.load_events_readonly(cfg)
    assert events["stats"]["malformed_lines"] == 1
