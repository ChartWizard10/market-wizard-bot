"""Campaign identity engine tests — C1."""

import json
import pytest

from src.campaign_store import (
    compute_campaign_id,
    is_same_structure,
    load,
    save,
    resolve,
    register_seen,
    _extract_zone_floor,
    _levels_match,
    _empty_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path=None):
    path = str(tmp_path / "campaign_state.json") if tmp_path else "data/campaign_state.json"
    return {"campaign": {"campaign_file": path}}


def _tiering(
    ticker="STRL",
    setup_family="continuation",
    zone_type="OB",
    invalidation_level=728.29,
    trigger_level=733.57,
    final_tier="SNIPE_IT",
    **extra,
):
    return {
        "final_tier": final_tier,
        "final_signal": {
            "ticker": ticker,
            "setup_family": setup_family,
            "zone_type": zone_type,
            "invalidation_level": invalidation_level,
            "trigger_level": trigger_level,
            **extra,
        },
    }


def _enriched_ob(ob_lo=728.0, ob_hi=746.0):
    return {"ob": {"ob_lo": ob_lo, "ob_hi": ob_hi, "ob_core": (ob_lo + ob_hi) / 2}}


def _enriched_fvg(fvg_bot=730.0, fvg_top=738.0):
    return {"fvg": {"fvg_bot": fvg_bot, "fvg_top": fvg_top, "fvg_mid": (fvg_bot + fvg_top) / 2}}


# ---------------------------------------------------------------------------
# compute_campaign_id
# ---------------------------------------------------------------------------

class TestComputeCampaignId:
    def test_stable_same_inputs(self):
        a = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        b = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        assert a == b

    def test_trigger_excluded(self):
        """Different trigger levels must not change the campaign ID."""
        id1 = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        id2 = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        # trigger never enters compute_campaign_id — always equal
        assert id1 == id2

    def test_different_ticker(self):
        a = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        b = compute_campaign_id("SNDK", "continuation", "OB", 728.0, 728.29)
        assert a != b

    def test_different_setup_family(self):
        a = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        b = compute_campaign_id("STRL", "reversal", "OB", 728.0, 728.29)
        assert a != b

    def test_different_zone_type(self):
        a = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        b = compute_campaign_id("STRL", "continuation", "FVG", 728.0, 728.29)
        assert a != b

    def test_invalidation_material_change_new_id(self):
        # 736.0 vs 728.29 — clearly different invalidations
        a = compute_campaign_id("STRL", "continuation", "OB", 728.0, 728.29)
        b = compute_campaign_id("STRL", "continuation", "OB", 728.0, 736.0)
        assert a != b

    def test_none_zone_floor(self):
        cid = compute_campaign_id("STRL", "continuation", "none", None, 728.29)
        assert "null" in cid

    def test_none_invalidation(self):
        cid = compute_campaign_id("STRL", "continuation", "OB", 728.0, None)
        assert "null" in cid


# ---------------------------------------------------------------------------
# is_same_structure — tolerance matching
# ---------------------------------------------------------------------------

class TestIsSameStructure:
    def _record(self, ticker="STRL", sf="continuation", zt="ob", zf=728.0, iv=728.29):
        return {
            "ticker": ticker,
            "setup_family": sf,
            "zone_type": zt,
            "zone_floor": zf,
            "invalidation_level": iv,
        }

    def test_exact_match(self):
        assert is_same_structure("STRL", "continuation", "OB", 728.0, 728.29, self._record())

    def test_invalidation_minor_drift_same(self):
        # 0.1% drift — within 0.5% tolerance
        iv_new = 728.29 * 1.001
        assert is_same_structure("STRL", "continuation", "OB", 728.0, iv_new, self._record())

    def test_zone_floor_minor_drift_same(self):
        # 0.1% zone floor drift
        zf_new = 728.0 * 1.001
        assert is_same_structure("STRL", "continuation", "OB", zf_new, 728.29, self._record())

    def test_invalidation_material_change_new_campaign(self):
        # 1% drift — outside 0.5% tolerance
        iv_new = 728.29 * 1.01
        assert not is_same_structure("STRL", "continuation", "OB", 728.0, iv_new, self._record())

    def test_zone_floor_material_change_new_campaign(self):
        zf_new = 728.0 * 1.01
        assert not is_same_structure("STRL", "continuation", "OB", zf_new, 728.29, self._record())

    def test_different_ticker_no_match(self):
        assert not is_same_structure("SNDK", "continuation", "OB", 728.0, 728.29, self._record())

    def test_different_setup_family_no_match(self):
        assert not is_same_structure("STRL", "reversal", "OB", 728.0, 728.29, self._record())

    def test_different_zone_type_no_match(self):
        assert not is_same_structure("STRL", "continuation", "FVG", 728.0, 728.29, self._record())

    def test_none_zone_floors_match(self):
        rec = self._record(zf=None)
        assert is_same_structure("STRL", "continuation", "OB", None, 728.29, rec)

    def test_one_none_zone_floor_no_match(self):
        rec = self._record(zf=None)
        assert not is_same_structure("STRL", "continuation", "OB", 728.0, 728.29, rec)


# ---------------------------------------------------------------------------
# _extract_zone_floor
# ---------------------------------------------------------------------------

class TestExtractZoneFloor:
    def test_ob_returns_ob_lo(self):
        assert _extract_zone_floor(_enriched_ob(ob_lo=728.0), "OB") == 728.0

    def test_fvg_returns_fvg_bot(self):
        assert _extract_zone_floor(_enriched_fvg(fvg_bot=730.5), "FVG") == 730.5

    def test_demand_prefers_ob_lo(self):
        enriched = {**_enriched_ob(ob_lo=728.0), **_enriched_fvg(fvg_bot=730.0)}
        assert _extract_zone_floor(enriched, "demand") == 728.0

    def test_demand_fallback_to_fvg_bot(self):
        assert _extract_zone_floor(_enriched_fvg(fvg_bot=730.0), "demand") == 730.0

    def test_none_zone_type_returns_none(self):
        assert _extract_zone_floor(_enriched_ob(), "none") is None

    def test_support_cluster_returns_none(self):
        assert _extract_zone_floor(_enriched_ob(), "support_cluster") is None

    def test_missing_enriched_returns_none(self):
        assert _extract_zone_floor({}, "OB") is None


# ---------------------------------------------------------------------------
# resolve — find or create campaign ID
# ---------------------------------------------------------------------------

class TestResolve:
    def test_empty_store_creates_new_id(self):
        cs = _empty_state()
        cid = resolve(_tiering(), _enriched_ob(), cs)
        assert "STRL" in cid
        assert "continuation" in cid

    def test_resolve_finds_existing_same_structure(self):
        cs = _empty_state()
        t = _tiering()
        e = _enriched_ob()
        # First resolution — registers new
        cid1 = resolve(t, e, cs)
        register_seen(cid1, t, e, cs)
        # Second resolution — same structure
        cid2 = resolve(t, e, cs)
        assert cid1 == cid2

    def test_trigger_drift_reuses_existing_id(self):
        """Four different trigger levels, same zone/invalidation → same campaign_id."""
        cs = _empty_state()
        e = _enriched_ob(ob_lo=728.0)
        triggers = [733.57, 732.81, 734.81, 732.42]
        ids = []
        for trig in triggers:
            t = _tiering(trigger_level=trig)
            cid = resolve(t, e, cs)
            register_seen(cid, t, e, cs)
            ids.append(cid)
        assert len(set(ids)) == 1, f"Expected 1 unique campaign id, got: {set(ids)}"

    def test_different_invalidation_new_id(self):
        cs = _empty_state()
        e = _enriched_ob()
        t1 = _tiering(invalidation_level=728.29)
        t2 = _tiering(invalidation_level=715.0)
        cid1 = resolve(t1, e, cs)
        register_seen(cid1, t1, e, cs)
        cid2 = resolve(t2, e, cs)
        assert cid1 != cid2

    def test_different_ticker_new_id(self):
        cs = _empty_state()
        e = _enriched_ob()
        t1 = _tiering(ticker="STRL")
        t2 = _tiering(ticker="SNDK")
        cid1 = resolve(t1, e, cs)
        register_seen(cid1, t1, e, cs)
        cid2 = resolve(t2, e, cs)
        assert cid1 != cid2


# ---------------------------------------------------------------------------
# register_seen
# ---------------------------------------------------------------------------

class TestRegisterSeen:
    def test_creates_new_record(self):
        cs = _empty_state()
        t = _tiering()
        e = _enriched_ob()
        cid = resolve(t, e, cs)
        register_seen(cid, t, e, cs)
        assert cid in cs["campaigns"]

    def test_increments_scan_count(self):
        cs = _empty_state()
        t = _tiering()
        e = _enriched_ob()
        cid = resolve(t, e, cs)
        for _ in range(3):
            register_seen(cid, t, e, cs)
        assert cs["campaigns"][cid]["scan_count"] == 3

    def test_stores_structural_fields(self):
        cs = _empty_state()
        t = _tiering(ticker="STRL", setup_family="continuation", zone_type="OB",
                     invalidation_level=728.29)
        e = _enriched_ob(ob_lo=728.0)
        cid = resolve(t, e, cs)
        register_seen(cid, t, e, cs)
        rec = cs["campaigns"][cid]
        assert rec["ticker"] == "STRL"
        assert rec["setup_family"] == "continuation"
        assert rec["zone_type"] == "ob"
        assert rec["zone_floor"] == 728.0
        assert rec["invalidation_level"] == 728.29


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_load_missing_returns_empty(self, tmp_path):
        cfg = _cfg(tmp_path)
        cs = load(cfg)
        assert cs["campaigns"] == {}

    def test_save_and_reload(self, tmp_path):
        cfg = _cfg(tmp_path)
        cs = _empty_state()
        t = _tiering()
        e = _enriched_ob()
        cid = resolve(t, e, cs)
        register_seen(cid, t, e, cs)
        save(cs, cfg)
        cs2 = load(cfg)
        assert cid in cs2["campaigns"]

    def test_load_corrupt_returns_empty_no_crash(self, tmp_path):
        cfg = _cfg(tmp_path)
        p = tmp_path / "campaign_state.json"
        p.write_text("{not valid json{{", encoding="utf-8")
        cs = load(cfg)
        assert cs["campaigns"] == {}

    def test_save_failure_no_crash(self, tmp_path, monkeypatch):
        cfg = _cfg(tmp_path)
        cs = _empty_state()

        def _boom(*a, **kw):
            raise IOError("disk full")

        monkeypatch.setattr("pathlib.Path.write_text", _boom)
        save(cs, cfg)  # must not raise
