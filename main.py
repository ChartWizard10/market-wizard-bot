"""Market Wizard Bot — production entry point.

Starts Discord, registers commands, and launches the auto-scan loop.
Secrets are read from environment variables only.

Production deep-analysis provider: Anthropic Claude (Opus 5). The scheduler
and telemetry Claude-named symbols are accurate — there is no adapter and no
secondary provider.
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


CREDENTIAL_SOURCE_MISSING = "MISSING"


def resolve_anthropic_api_key() -> tuple[str | None, str]:
    """Return (key, source) for the Anthropic credential.

        1. ANTHROPIC_API_KEY — the standard explicit name
        2. ANTHROPIC_KEY     — compatibility alias for the historical Railway
                               secret, so restoring the provider does not force
                               an unnecessary secret rotation

    Blank or whitespace-only values count as absent. No other provider's
    credential is a model credential here — Anthropic is the sole provider and
    there is no cross-provider fallback. The key itself is never logged or
    returned in any diagnostic; only its source name is.
    """
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value, name
    return None, CREDENTIAL_SOURCE_MISSING


def validate_startup(config: dict) -> dict:
    """Validate runtime environment without creating network clients."""
    errors: list[str] = []
    warnings: list[str] = []

    if not os.environ.get("DISCORD_TOKEN"):
        errors.append("DISCORD_TOKEN is not set — bot cannot authenticate with Discord")

    key, _source = resolve_anthropic_api_key()
    if not key:
        warnings.append(
            "Anthropic API key is not set (ANTHROPIC_API_KEY, or ANTHROPIC_KEY) — "
            "!scan and !analyze model analysis will fail gracefully"
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


def build_bot(config: dict) -> tuple:
    """Build Discord plus the native Anthropic client.

    The scheduler calls `client.messages.create(...)` through
    `src.claude_client`, which is exactly the Anthropic Messages contract — so
    the real client is passed straight through with no adapter in between.
    """
    anthropic_key, credential_source = resolve_anthropic_api_key()
    model_client = None
    if anthropic_key:
        try:
            from anthropic import AsyncAnthropic
            model_client = AsyncAnthropic(api_key=anthropic_key)
            from src.claude_client import resolve_claude_model
            selected_model, model_source = resolve_claude_model(config)
            log.info(
                "CLAUDE_RUNTIME_READY: provider=anthropic credential_source=%s "
                "model=%s model_source=%s",
                credential_source, selected_model, model_source,
            )
        except Exception as exc:
            log.error("Could not create Anthropic client: %s", exc)

    system_prompt = None
    try:
        from src.claude_client import load_system_prompt
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
            "`!archivestatus` — Read-only CAP-40D archive health/persistence anchor (operator-gated)\n"
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

    @bot.command(name="archivestatus")
    async def archivestatus_cmd(ctx) -> None:
        """Operator-gated, read-only CAP-40D runtime archive probe."""
        from src import audit_access
        from src import research_archive_health

        user_id = getattr(getattr(ctx, "author", None), "id", None)
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        try:
            auth = audit_access.is_authorized(
                config, user_id=user_id, channel_id=channel_id
            )
            if not auth.get("allowed"):
                await ctx.send("Archive status access denied.")
                return
            result = research_archive_health.snapshot(config)
            for chunk in chunk_message(research_archive_health.render(result)):
                await ctx.send(chunk)
        except Exception as exc:
            log.error("!archivestatus error: %s", exc)
            await ctx.send(f"Archive status error: {type(exc).__name__}")

    @bot.command(name="scan")
    async def scan_cmd(ctx) -> None:
        if model_client is None or system_prompt is None:
            await ctx.send(
                "ERROR: Claude model not configured"
                " (Anthropic API key missing or system prompt not found)"
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
                "ERROR: Claude model not configured"
                " (Anthropic API key missing or system prompt not found)"
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
            from src.claude_client import resolve_claude_model
            ticker_file = config.get("scan", {}).get("ticker_file", "config/tickers.txt")
            count = load_tickers(ticker_file)["validation_summary"]["valid_ticker_count"]
            scan_cfg = config.get("scan", {})
            selected_model, model_source = resolve_claude_model(config)
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
