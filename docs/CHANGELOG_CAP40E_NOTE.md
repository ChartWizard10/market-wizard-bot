# CAP-40E change note

- Adds read-only operator command `!archivestatus` for CAP-40D deployment health and persistence anchors.
- Reuses existing `audit_access` allow-list; unauthorized users/channels are denied.
- Reports bounded partition metadata, oldest/latest scan-id anchors, byte counts, current-session partition presence, malformed-tail count and read-error class.
- Explicitly states that a single snapshot does not prove Railway persistence; pre/post-restart anchor comparison is required.
- Adds no archive write, market-data call, GPT-5.6 call, tier/capital/routing/cooldown/suppression authority or arbitrary filesystem path input.
- Production stays at 814 symbols, 15-minute cadence, cap 30, Phase-14V 9,000-trace ceiling, and real 4H remains `SHADOW_EVIDENCE_ONLY`.
