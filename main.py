"""Market Wizard Bot — production entry point.

Starts the Discord bot, registers commands, and launches the auto-scan loop.
Secrets are read from environment variables only — never hardcoded.
"""

import asyncio
import logging
import os
import sys

import discord
from discord.ext import commands
import yaml

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(path: str = "config/doctrine_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Startup validation (pure — no side effects, testable without a live bot)
# ---------------------------------------------------------------------------

def validate_startup(config: dict) -> dict:
    """Check required environment variables.

    Returns:
        {ok: bool, errors: list[str], warnings: list[str]}

    DISCORD_TOKEN missing → hard error (bot cannot authenticate).
    ANTHROPIC_KEY missing → warning only (Claude commands fail gracefully).
    """
    errors: list   = []
    warnings: list = []

    if not os.environ.get("DISCORD_TOKEN"):
        errors.append("DISCORD_TOKEN is not set — bot cannot authenticate with Discord")

    if not os.environ.get("ANTHROPIC_KEY"):
        warnings.append(
            "ANTHROPIC_KEY is not set — !scan and !analyze will fail gracefully"
        )

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Summary formatter (top-level so it can be tested without a running bot)
# ---------------------------------------------------------------------------

def format_scan_summary(summary: dict) -> str:
    """Format a scan summary dict into a short Discord message."""
    status = summary.get("status", "unknown")

    if status == "skipped":
        return f"Scan skipped: {summary.get('reason', 'unknown reason')}"

    if status == "aborted":
        return f"Scan aborted: {summary.get('error', 'unknown error')}"

    tier  = summary.get("final_tier_counts", {})
    top   = summary.get("top_candidates", [])[:5]
    top_s = ", ".join(f"{c['ticker']}({c['score']})" for c in top) if top else "none"

    return (
        f"**Scan Summary** `{summary.get('scan_id', '?')}`\n"
        f"Tickers: {summary.get('total_tickers_input', 0)}"
        f" | Data failures: {summary.get('total_data_failures', 0)}\n"
        f"Prefilter passed: {summary.get('total_prefilter_passed', 0)}"
        f" | Claude candidates: {summary.get('total_claude_candidates', 0)}\n"
        f"Tiers — SNIPE: {tier.get('SNIPE_IT', 0)}"
        f"  STARTER: {tier.get('STARTER', 0)}"
        f"  NEAR: {tier.get('NEAR_ENTRY', 0)}"
        f"  WAIT: {tier.get('WAIT', 0)}\n"
        f"Alerts sent: {summary.get('alerts_sent', 0)}"
        f" | Suppressed: {summary.get('alerts_suppressed', 0)}\n"
        f"Duration: {summary.get('duration_seconds', 0):.1f}s\n"
        f"Top: {top_s}"
    )


# ---------------------------------------------------------------------------
# Bot setup and command registration
# ---------------------------------------------------------------------------

def build_bot(config: dict) -> tuple:
    """Build and configure the Discord bot.

    Returns (bot, anthropic_client, system_prompt).
    anthropic_client is None if ANTHROPIC_KEY is absent.
    system_prompt is None if the prompt file cannot be loaded.
    """
    anthropic_key = os.environ.get("ANTHROPIC_KEY")

    # Anthropic client
    anthropic_client = None
    if anthropic_key:
        try:
            import anthropic
            anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_key)
        except Exception as exc:
            log.error("Could not create Anthropic client: %s", exc)

    # System prompt
    system_prompt = None
    try:
        from src.claude_client import load_system_prompt
        system_prompt = load_system_prompt("prompts/market_wizard_system.md")
    except Exception as exc:
        log.error("Could not load system prompt: %s", exc)

    # Discord bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    return bot, anthropic_client, system_prompt


# ---------------------------------------------------------------------------
# Register commands onto a bot instance
# ---------------------------------------------------------------------------

def register_commands(
    bot: commands.Bot,
    config: dict,
    anthropic_client,
    system_prompt: str | None,
) -> dict:
    """Register all Discord commands. Returns a mutable state dict shared by commands."""
    from src import scheduler
    from src.discord_alerts import chunk_message

    shared: dict = {
        "last_scan_summary":  {},
        "scheduler_enabled":  False,
        "scan_task":          None,
    }

    # ------------------------------------------------------------------
    # Auto-scan loop (plain asyncio task — interval from config)
    # ------------------------------------------------------------------

    async def _auto_scan_loop() -> None:
        interval_minutes = config.get("scan", {}).get("interval_minutes", 15)
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)
                if scheduler.is_market_hours(config):
                    log.info("Starting scheduled scan")
                    summary = await scheduler.run_full_scan(
                        bot, config, system_prompt, anthropic_client
                    )
                    shared["last_scan_summary"] = summary
                else:
                    log.debug("Scheduled scan skipped — outside market hours")
            except asyncio.CancelledError:
                log.info("Auto-scan loop cancelled")
                break
            except Exception as exc:
                log.error("Auto-scan loop error: %s", exc)

    # ------------------------------------------------------------------
    # on_ready
    # ------------------------------------------------------------------

    @bot.event
    async def on_ready() -> None:
        log.info("Bot ready: %s (id=%s)", bot.user.name, bot.user.id)
        task = asyncio.create_task(_auto_scan_loop())
        shared["scan_task"]          = task
        shared["scheduler_enabled"]  = True
        interval = config.get("scan", {}).get("interval_minutes", 15)
        log.info("Auto-scan task started: interval=%dm", interval)

    # ------------------------------------------------------------------
    # !help
    # ------------------------------------------------------------------

    @bot.command(name="help")
    async def help_cmd(ctx) -> None:
        await ctx.send(
            "**Market Wizard Bot Commands**\n"
            "`!scan` — Full scan of ticker universe (respects market hours)\n"
            "`!analyze TICKER` — Single-ticker analysis (bypasses dedup cooldown)\n"
            "`!status` — Bot status and last scan summary\n"
            "`!autoscan start` — Enable scheduled auto-scan\n"
            "`!autoscan stop` — Disable scheduled auto-scan\n"
        )

    # ------------------------------------------------------------------
    # !scan
    # ------------------------------------------------------------------

    @bot.command(name="scan")
    async def scan_cmd(ctx) -> None:
        if anthropic_client is None or system_prompt is None:
            await ctx.send(
                "ERROR: Claude not configured"
                " (ANTHROPIC_KEY missing or system prompt not found)"
            )
            return

        await ctx.send("Starting manual scan…")
        try:
            summary = await scheduler.run_full_scan(
                bot, config, system_prompt, anthropic_client, is_manual=True
            )
            shared["last_scan_summary"] = summary
            for chunk in chunk_message(format_scan_summary(summary)):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!scan error: %s", exc)
            await ctx.send(f"Scan error: {type(exc).__name__}")

    # ------------------------------------------------------------------
    # !analyze TICKER
    # ------------------------------------------------------------------

    @bot.command(name="analyze")
    async def analyze_cmd(ctx, ticker: str = "") -> None:
        if not ticker:
            await ctx.send("Usage: `!analyze TICKER`  e.g. `!analyze AAPL`")
            return

        ticker = ticker.upper().strip()

        if anthropic_client is None or system_prompt is None:
            await ctx.send(
                "ERROR: Claude not configured"
                " (ANTHROPIC_KEY missing or system prompt not found)"
            )
            return

        await ctx.send(f"Analyzing {ticker}…")
        try:
            result = await scheduler.run_analyze(
                ticker, bot, config, system_prompt, anthropic_client
            )

            status = result.get("status")
            if status == "skipped":
                await ctx.send(f"{ticker}: skipped — previous scan still running")
                return
            if status in ("error", "data_failure", "claude_error"):
                detail = result.get("error") or result.get("error_type", "")
                await ctx.send(f"{ticker}: {status} — {detail}")
                return

            final_tier = result.get("final_tier", "WAIT")
            alert_sent = result.get("alert_sent", False)
            dedup_rsn  = result.get("dedup_reason", "")
            await ctx.send(
                f"**{ticker}** — {final_tier}\n"
                f"Alert sent: {alert_sent}  |  Dedup: {dedup_rsn}\n"
                f"Scan ID: {result.get('scan_id', '')}"
            )
        except Exception as exc:
            log.error("!analyze error for %s: %s", ticker, exc)
            await ctx.send(f"Analyze error for {ticker}: {type(exc).__name__}")

    # ------------------------------------------------------------------
    # !status
    # ------------------------------------------------------------------

    @bot.command(name="status")
    async def status_cmd(ctx) -> None:
        try:
            from src.market_data import load_tickers
            ticker_file = config.get("scan", {}).get("ticker_file", "config/tickers.txt")
            tkr = load_tickers(ticker_file)
            count = tkr["validation_summary"]["valid_ticker_count"]

            scan_cfg = config.get("scan", {})
            state_file = config.get("state", {}).get("state_file", "data/alert_state.json")
            in_hours   = scheduler.is_market_hours(config)

            msg = (
                f"**Market Wizard Bot Status**\n"
                f"Tickers loaded: {count}\n"
                f"Scheduler: {'enabled' if shared['scheduler_enabled'] else 'disabled'}\n"
                f"Scan interval: {scan_cfg.get('interval_minutes', 15)}m\n"
                f"Market hours only: {scan_cfg.get('market_hours_only', True)}"
                f"  ({scan_cfg.get('market_open', '09:35')}–"
                f"{scan_cfg.get('market_close', '15:55')} ET)\n"
                f"In market hours now: {in_hours}\n"
                f"State store: {state_file}\n"
            )

            last = shared["last_scan_summary"]
            if last:
                msg += (
                    f"\n**Last Scan**\n"
                    f"ID: {last.get('scan_id', '—')}\n"
                    f"Status: {last.get('status', '—')}\n"
                    f"Alerts sent: {last.get('alerts_sent', 0)}\n"
                    f"Duration: {last.get('duration_seconds', 0):.1f}s\n"
                )
            else:
                msg += "\nNo scan completed yet."

            await ctx.send(msg)
        except Exception as exc:
            log.error("!status error: %s", exc)
            await ctx.send(f"Status error: {type(exc).__name__}")

    # ------------------------------------------------------------------
    # !autoscan start | stop
    # ------------------------------------------------------------------

    @bot.command(name="autoscan")
    async def autoscan_cmd(ctx, action: str = "") -> None:
        action = action.lower()

        if action == "start":
            task = shared.get("scan_task")
            if task and not task.done():
                await ctx.send("Auto-scan already running.")
                return
            t = asyncio.create_task(_auto_scan_loop())
            shared["scan_task"]         = t
            shared["scheduler_enabled"] = True
            interval = config.get("scan", {}).get("interval_minutes", 15)
            await ctx.send(f"Auto-scan started (interval: {interval}m)")

        elif action == "stop":
            task = shared.get("scan_task")
            if task and not task.done():
                task.cancel()
            shared["scheduler_enabled"] = False
            await ctx.send("Auto-scan stopped.")

        else:
            await ctx.send("Usage: `!autoscan start` or `!autoscan stop`")

    return shared


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        config = load_config()
    except Exception as exc:
        print(f"FATAL: Could not load config: {exc}", file=sys.stderr)
        sys.exit(1)

    startup = validate_startup(config)

    for w in startup["warnings"]:
        log.warning(w)

    if not startup["ok"]:
        for e in startup["errors"]:
            log.error("STARTUP_ERROR: %s", e)
        sys.exit(1)

    discord_token = os.environ["DISCORD_TOKEN"]

    bot, anthropic_client, system_prompt = build_bot(config)
    register_commands(bot, config, anthropic_client, system_prompt)

    log.info("Starting Market Wizard Bot")
    bot.run(discord_token)


if __name__ == "__main__":
    main()
