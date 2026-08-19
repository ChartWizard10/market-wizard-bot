"""Config acceptance criteria tests — production activation."""

import yaml


def _load() -> dict:
    with open("config/doctrine_config.yaml") as f:
        return yaml.safe_load(f)


def test_config_loads():
    cfg = _load()
    assert isinstance(cfg, dict)
    for key in ("scan", "prefilter", "tiers", "discord", "model", "state"):
        assert key in cfg


def test_production_model_is_openai_gpt56():
    cfg = _load()
    assert cfg["model"]["provider"] == "openai"
    assert cfg["model"]["name"] == "gpt-5.6"
    assert cfg["model"]["reasoning_effort"] == "medium"


def test_candidate_cap_remains_30_during_ai1():
    cfg = _load()
    assert cfg["prefilter"]["max_claude_candidates_per_scan"] == 30


def test_scoring_weights_sum():
    cfg = _load()
    weights = cfg["prefilter"]["scoring_weights"]
    total = sum(weights.values())
    assert total == 100, f"scoring_weights sum to {total}, expected 100"


def test_lookback_period():
    cfg = _load()
    period = cfg["data"]["lookback_period"]
    assert isinstance(period, str)
    if period.endswith("mo"):
        months = int(period[:-2])
        assert months >= 12, f"lookback_period {period} < 12 months"
    elif period.endswith("y"):
        years = int(period[:-1])
        assert years >= 1, f"lookback_period {period} < 1 year"
    else:
        raise AssertionError(f"Unrecognised lookback_period format: {period!r}")


def test_disabled_indicators_complete():
    cfg = _load()
    disabled = cfg.get("disabled_indicators", [])
    required = {"rsi", "macd", "bollinger_bands", "stochastic"}
    missing = required - set(disabled)
    assert not missing, f"disabled_indicators missing: {missing}"


def test_discord_channel_keys_exist():
    cfg = _load()
    disc = cfg.get("discord", {})
    for key in ("snipe_channel_id", "starter_channel_id", "near_entry_channel_id"):
        assert key in disc, f"discord.{key} key is absent from config"


def test_tier_score_floors_ordered():
    cfg = _load()
    snipe = cfg["tiers"]["snipe_it"]["min_score"]
    starter = cfg["tiers"]["starter"]["min_score"]
    near = cfg["tiers"]["near_entry"]["min_score"]
    pf = cfg["prefilter"]["prefilter_min_score"]
    assert snipe > starter
    assert starter > near
    assert near > pf
