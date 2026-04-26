"""Config acceptance criteria tests — Phase 9 activation."""

import yaml


def _load() -> dict:
    with open("config/doctrine_config.yaml") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1. Config loads without error
# ---------------------------------------------------------------------------

def test_config_loads():
    cfg = _load()
    assert isinstance(cfg, dict)
    assert "scan" in cfg
    assert "prefilter" in cfg
    assert "tiers" in cfg
    assert "discord" in cfg
    assert "claude" in cfg
    assert "state" in cfg


# ---------------------------------------------------------------------------
# 2. Scoring weights sum to exactly 100
# ---------------------------------------------------------------------------

def test_scoring_weights_sum():
    cfg = _load()
    weights = cfg["prefilter"]["scoring_weights"]
    total = sum(weights.values())
    assert total == 100, f"scoring_weights sum to {total}, expected 100"


# ---------------------------------------------------------------------------
# 3. Lookback period resolves to ≥ 12 months of data
# ---------------------------------------------------------------------------

def test_lookback_period():
    cfg = _load()
    period = cfg["data"]["lookback_period"]
    assert isinstance(period, str)
    # Accept "18mo", "1y", "2y", "24mo" etc. — at least 12 months
    if period.endswith("mo"):
        months = int(period[:-2])
        assert months >= 12, f"lookback_period {period} < 12 months"
    elif period.endswith("y"):
        years = int(period[:-1])
        assert years >= 1, f"lookback_period {period} < 1 year"
    else:
        raise AssertionError(f"Unrecognised lookback_period format: {period!r}")


# ---------------------------------------------------------------------------
# 4. disabled_indicators list is complete
# ---------------------------------------------------------------------------

def test_disabled_indicators_complete():
    cfg = _load()
    disabled = cfg.get("disabled_indicators", [])
    required = {"rsi", "macd", "bollinger_bands", "stochastic"}
    missing = required - set(disabled)
    assert not missing, f"disabled_indicators missing: {missing}"


# ---------------------------------------------------------------------------
# 5. Discord channel keys exist (null values are permitted)
# ---------------------------------------------------------------------------

def test_discord_channel_keys_exist():
    cfg = _load()
    disc = cfg.get("discord", {})
    for key in ("snipe_channel_id", "starter_channel_id", "near_entry_channel_id"):
        assert key in disc, f"discord.{key} key is absent from config"


# ---------------------------------------------------------------------------
# 6. Tier score floors are strictly ordered
# ---------------------------------------------------------------------------

def test_tier_score_floors_ordered():
    cfg = _load()
    snipe   = cfg["tiers"]["snipe_it"]["min_score"]
    starter = cfg["tiers"]["starter"]["min_score"]
    near    = cfg["tiers"]["near_entry"]["min_score"]
    pf      = cfg["prefilter"]["prefilter_min_score"]
    assert snipe > starter, f"snipe min_score {snipe} ≤ starter {starter}"
    assert starter > near,  f"starter min_score {starter} ≤ near_entry {near}"
    assert near > pf,       f"near_entry min_score {near} ≤ prefilter floor {pf}"
