"""Phase 14Y integration firewall for !analyze Structural Atlas."""

from pathlib import Path


def test_analyze_full_mode_appends_structural_atlas_without_second_scan():
    src = Path("main.py").read_text(encoding="utf-8")
    analyze = src[src.index('@bot.command(name="analyze")'):src.index('@bot.command(name="status")')]
    assert "structural_atlas.render_structural_atlas(result)" in analyze
    assert 'audit_text + "\\n" + atlas_text' in analyze
    assert analyze.count("scheduler.run_analyze(") == 1
    assert "run_full_scan(" not in analyze


def test_analyze_json_contains_structural_atlas():
    src = Path("main.py").read_text(encoding="utf-8")
    analyze = src[src.index('@bot.command(name="analyze")'):src.index('@bot.command(name="status")')]
    assert 'payload["structural_atlas"] = structural_atlas.build_structural_atlas(result)' in analyze


def test_compact_mode_remains_legacy_compact_surface():
    src = Path("main.py").read_text(encoding="utf-8")
    analyze = src[src.index('@bot.command(name="analyze")'):src.index('@bot.command(name="status")')]
    compact = analyze.split('if mode == "compact":', 1)[1].split('elif mode == "json":', 1)[0]
    assert "render_operator_audit_compact(result)" in compact
    assert "structural_atlas" not in compact


def test_atlas_does_not_touch_autoscan_or_alert_routing():
    src = Path("main.py").read_text(encoding="utf-8")
    before_analyze = src[:src.index('@bot.command(name="analyze")')]
    assert "structural_atlas" not in before_analyze
    assert "discord_alerts.send_alert" not in src
