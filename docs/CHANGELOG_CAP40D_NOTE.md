# CAP-40D change note

- Adds a separate research-only `.state/research_archive/` so CAP-40C and R4H-3C forward cohorts survive Phase-14V's bounded 9,000-trace ring rollover.
- Archives only whitelisted already-built scan evidence: identity/rank, VELOCITY observation, real-4H shadow projection and CAP-40 boundary observation.
- Uses date-partitioned JSONL, 120-day retention and a 10 MiB daily safety ceiling.
- Archive write failure is isolated from market judgment, state, Discord and normal Phase-14V persistence.
- VELOCITY-1D and CAP-40B dataset CLIs may consume either a saved telemetry ledger or the CAP-40D archive directory.
- Production cap remains 30, cadence 15 minutes, universe 814, real 4H `SHADOW_EVIDENCE_ONLY`; no strategy threshold, capital, routing, cooldown or setup-family admission change.
- Railway durable-volume persistence for `.state/research_archive/` is an operational validation requirement; repository code cannot prove it.
