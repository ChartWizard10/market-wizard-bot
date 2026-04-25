"""Market Wizard Bot — entry point. Phase 1 skeleton only."""
import os
import sys
import yaml


def load_config(path: str = "config/doctrine_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    print("Market Wizard Bot — skeleton ok")
    print(f"  model:          {config['claude']['model']}")
    print(f"  lookback:       {config['data']['lookback_period']}")
    print(f"  scan interval:  {config['scan']['interval_minutes']}m")
    print(f"  disabled:       {config['disabled_indicators']}")

    discord_token = os.environ.get("DISCORD_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_KEY")

    if not discord_token or not anthropic_key:
        print("WARNING: DISCORD_TOKEN or ANTHROPIC_KEY not set — bot cannot start.")
        sys.exit(0)


if __name__ == "__main__":
    main()
