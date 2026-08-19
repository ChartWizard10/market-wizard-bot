"""Market Wizard Bot — production entry point.

Starts Discord, registers commands, and launches the auto-scan loop.
Secrets are read from environment variables only.

Phase AI-1 production provider: OpenAI GPT-5.6. Historical Claude-named
scheduler/telemetry symbols remain temporarily as compatibility naming only.
"""

import asyncio
import logging
import os
import sys

import discord
from discord.ext import commands
import yaml

log = logging.getLogger(__name__)


def load_config(path: str = "config/doctrine_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def validate_startup(config: dict) -> dict:
    """Validate runtime environment without creating network clients."""
    errors: list[str] = []
    warnings: list[str] = []

    if not os.environ.get("DISCORD_TOKEN"):
        errors.append("DISCORD_TOKEN is not set — bot cannot authenticate with Discord")

    if not os.environ.get("OPENAI_API_KEY"):
        # The legacy name appears only to make the historical startup regression
        # explicit: ANTHROPIC_KEY is NOT a substitute production credential.
        warnings.append(
            "OPENAI_API_KEY is not set — !scan and !analyze will fail gracefully; "
            "legacy ANTHROPIC_KEY is not used for production authentication"
        )

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def format_scan_summary(summary: dict) -> str:
    status = summary.get("status", "unknown")
    if status == "skipped":
        return f"Scan skipped: {summary.get('reason', 'unknown reason')}"
    if status == "aborted":
        return f"Scan aborted: {summary.get('error', 'unknown error')}"

    tier = summary.get("final_tier_counts", {})
    top = summary.get("top_candidates", [])[:5]
    top_s = ", ".join(f"{c['ticker']}({c['score']})" for c in top) if top else "none"
    return (
        f"**Scan Summary** `{summary.get('scan_id', '?')}`\n"
        f"Tickers: {summary.get('total_tickers_input', 0)}"
        f" | Data failures: {summary.get('total_data_failures', 0)}\n"
        f"Prefilter passed: {summary.get('total_prefilter_passed', 0)}"
        f" | GPT-5.6 candidates: {summary.get('total_claude_candidates', 0)}\n"
        f"Tiers — SNIPE: {tier.get('SNIPE_IT', 0)}"
        f"  STARTER: {tier.get('STARTER', 0)}"
        f"  NEAR: {tier.get('NEAR_ENTRY', 0)}"
        f"  WAIT: {tier.get('WAIT', 0)}\n"
        f"Alerts sent: {summary.get('alerts_sent', 0)}"
        f" | Suppressed: {summary.get('alerts_suppressed', 0)}\n"
        f"Duration: {summary.get('duration_seconds', 0):.1f}s\n"
        f"Top: {top_s}"
    )


def build_bot(config: dict) -> tuple:
    """Build Discord plus the OpenAI-backed scheduler compatibility client."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    model_client = None
    if openai_key:
        try:
            from openai import AsyncOpenAI
            from src.openai_scheduler_compat import OpenAISchedulerCompatClient
            model_client = OpenAISchedulerCompatClient(
                AsyncOpenAI(api_key=openai_key), config
            )
        except Exception as exc:
            log.error("Could not create OpenAI GPT-5.6 client: %s", exc)

    system_prompt = None
    try:
        from src.model_client import load_system_prompt
        system_prompt = load_system_prompt("prompts/market_wizard_system.md")
    except Exception as exc:
        log.error("Could not load system prompt: %s", exc)

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
    return bot, model_client, system_prompt


def register_commands(
    bot: commands.Bot,
    config: dict,
    model_client,
    system_prompt: str | None,
) -> dict:
    from src import scheduler
    from src.discord_alerts import chunk_message

    shared = {"last_scan_summary": {}, "scheduler_enabled": False, "scan_task": None}

    async def _auto_scan_loop() -> None:
        interval_minutes = config.get("scan", {}).get("interval_minutes", 15)
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)
                if scheduler.is_market_hours(config):
                    log.info("Starting scheduled scan")
                    summary = await scheduler.run_full_scan(
                        bot, config, system_prompt, model_client
                    )
                    shared["last_scan_summary"] = summary
                else:
                    log.debug("Scheduled scan skipped — outside market hours")
            except asyncio.CancelledError:
                log.info("Auto-scan loop cancelled")
                break
            except Exception as exc:
                log.error("Auto-scan loop error: %s", exc)

    @bot.event
    async def on_ready() -> None:
        log.info("Bot ready: %s (id=%s)", bot.user.name, bot.user.id)
        task = asyncio.create_task(_auto_scan_loop())
        shared["scan_task"] = task
        shared["scheduler_enabled"] = True
        log.info(
            "Auto-scan task started: interval=%dm",
            config.get("scan", {}).get("interval_minutes", 15),
        )

    @bot.command(name="help")
    async def help_cmd(ctx) -> None:
        await ctx.send(
            "**Market Wizard Bot Commands**\n"
            "`!scan` — Full scan of ticker universe (respects market hours)\n"
            "`!analyze TICKER` — Single-ticker analysis (bypasses dedup cooldown)\n"
            "`!status` — Bot status and last scan summary\n"
            "`!autoscan start` — Enable scheduled auto-scan\n"
            "`!autoscan stop` — Disable scheduled auto-scan\n"
            "`!audit <scan_id|TICKER> [json]` — Read-only alert_history evidence (operator-gated)\n"
            "`!auditready [rows] [json]` — Radar: recent rows ready for SNIPE review but not promoted (operator-gated)\n"
            "`!auditshy [rows] [json]` — Funnel: where SNIPE/STARTER opportunity is capped or blocked (operator-gated)\n"
        )

    @bot.command(name="audit")
    async def audit_cmd(ctx, *, args: str = "") -> None:
        from src import audit_access
        user_id = getattr(getattr(ctx, "author", None), "id", None)
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        try:
            result = audit_access.run_audit(config, args, user_id=user_id, channel_id=channel_id)
            for chunk in result.get("messages", []):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!audit error: %s", exc)
            await ctx.send(f"Audit error: {type(exc).__name__}")

    @bot.command(name="auditready")
    async def auditready_cmd(ctx, *, args: str = "") -> None:
        from src import audit_access
        user_id = getattr(getattr(ctx, "author", None), "id", None)
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        try:
            result = audit_access.run_auditready(config, args, user_id=user_id, channel_id=channel_id)
            for chunk in result.get("messages", []):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!auditready error: %s", exc)
            await ctx.send(f"Auditready error: {type(exc).__name__}")

    @bot.command(name="auditshy")
    async def auditshy_cmd(ctx, *, args: str = "") -> None:
        from src import audit_access
        user_id = getattr(getattr(ctx, "author", None), "id", None)
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        try:
            result = audit_access.run_auditshy(config, args, user_id=user_id, channel_id=channel_id)
            for chunk in result.get("messages", []):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!auditshy error: %s", exc)
            await ctx.send(f"Auditshy error: {type(exc).__name__}")

    @bot.command(name="scan")
    async def scan_cmd(ctx) -> None:
        if model_client is None or system_prompt is None:
            await ctx.send(
                "ERROR: GPT-5.6 not configured"
                " (OPENAI_API_KEY missing or system prompt not found)"
            )
            return
        await ctx.send("Starting manual scan…")
        try:
            summary = await scheduler.run_full_scan(
                bot, config, system_prompt, model_client, is_manual=True
            )
            shared["last_scan_summary"] = summary
            for chunk in chunk_message(format_scan_summary(summary)):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!scan error: %s", exc)
            await ctx.send(f"Scan error: {type(exc).__name__}")

    @bot.command(name="analyze")
    async def analyze_cmd(ctx, ticker: str = "") -> None:
        if not ticker:
            await ctx.send("Usage: `!analyze TICKER`  e.g. `!analyze AAPL`")
            return
        ticker = ticker.upper().strip()
        if model_client is None or system_prompt is None:
            await ctx.send(
                "ERROR: GPT-5.6 not configured"
                " (OPENAI_API_KEY missing or system prompt not found)"
            )
            return
        await ctx.send(f"Analyzing {ticker}…")
        try:
            result = await scheduler.run_analyze(
                ticker, bot, config, system_prompt, model_client
            )
            status = result.get("status")
            if status == "skipped":
                await ctx.send(f"{ticker}: skipped — previous scan still running")
                return
            if status in ("error", "data_failure", "claude_error", "model_error"):
                detail = result.get("error") or result.get("error_type", "")
                display_status = "model_error" if status == "claude_error" else status
                await ctx.send(f"{ticker}: {display_status} — {detail}")
                return
            await ctx.send(
                f"**{ticker}** — {result.get('final_tier', 'WAIT')}\n"
                f"Alert sent: {result.get('alert_sent', False)}  |  "
                f"Dedup: {result.get('dedup_reason', '')}\n"
                f"Scan ID: {result.get('scan_id', '')}"
            )
        except Exception as exc:
            log.error("!analyze error for %s: %s", ticker, exc)
            await ctx.send(f"Analyze error for {ticker}: {type(exc).__name__}")

    @bot.command(name="status")
    async def status_cmd(ctx) -> None:
        try:
            from src.market_data import load_tickers
            from src.model_client import resolve_model
            ticker_file = config.get("scan", {}).get("ticker_file", "config/tickers.txt")
            count = load_tickers(ticker_file)["validation_summary"]["valid_ticker_count"]
            scan_cfg = config.get("scan", {})
            selected_model, model_source = resolve_model(config)
            msg = (
                f"**Market Wizard Bot Status**\n"
                f"Tickers loaded: {count}\n"
                f"Model: {selected_model} ({model_source})\n"
                f"Scheduler: {'enabled' if shared['scheduler_enabled'] else 'disabled'}\n"
                f"Scan interval: {scan_cfg.get('interval_minutes', 15)}m\n"
                f"Market hours only: {scan_cfg.get('market_hours_only', True)}"
                f"  ({scan_cfg.get('market_open', '09:35')}–{scan_cfg.get('market_close', '15:55')} ET)\n"
                f"In market hours now: {scheduler.is_market_hours(config)}\n"
                f"State store: {config.get('state', {}).get('state_file', 'data/alert_state.json')}\n"
            )
            last = shared["last_scan_summary"]
            if last:
                msg += (
                    f"\n**Last Scan**\nID: {last.get('scan_id', '—')}\n"
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

    @bot.command(name="autoscan")
    async def autoscan_cmd(ctx, action: str = "") -> None:
        action = action.lower()
        if action == "start":
            task = shared.get("scan_task")
            if task and not task.done():
                await ctx.send("Auto-scan already running.")
                return
            shared["scan_task"] = asyncio.create_task(_auto_scan_loop())
            shared["scheduler_enabled"] = True
            await ctx.send(
                f"Auto-scan started (interval: {config.get('scan', {}).get('interval_minutes', 15)}m)"
            )
        elif action == "stop":
            task = shared.get("scan_task")
            if task and not task.done():
                task.cancel()
            shared["scheduler_enabled"] = False
            await ctx.send("Auto-scan stopped.")
        else:
            await ctx.send("Usage: `!autoscan start` or `!autoscan stop`")

    return shared


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
    for warning in startup["warnings"]:
        log.warning(warning)
    if not startup["ok"]:
        for error in startup["errors"]:
            log.error("STARTUP_ERROR: %s", error)
        sys.exit(1)

    bot, model_client, system_prompt = build_bot(config)
    register_commands(bot, config, model_client, system_prompt)
    log.info("Starting Market Wizard Bot")
    bot.run(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    main()
