# Phase CAP-40E — Archive Operational Health Probe

## Purpose

CAP-40D solved the repository-side retention problem by adding a long-horizon forward research archive. The remaining proof is operational: does the deployed Railway runtime actually preserve that archive across restart/redeploy?

CAP-40E adds a **read-only, operator-gated** Discord probe so this can be checked without shell access and without granting research evidence any trading authority.

Command:

`!archivestatus`

## What the probe reports

The command reports only bounded archive-health metadata:

- configured archive path;
- enabled/disabled state;
- health status (`READY`, `DEGRADED`, `EMPTY`, `MISSING_DIRECTORY`, `PATH_COLLISION`, `DISABLED`);
- partition count;
- oldest/newest partition date;
- total and latest-partition bytes;
- current America/New_York session date and whether that partition exists;
- oldest retained scan-id anchor;
- latest retained scan-id/timestamp/trace-count anchor;
- malformed trailing-line count for the latest partition;
- read-error class if applicable.

It explicitly reports:

`Durability proven by this snapshot: NO`

A single snapshot proves presence, not persistence. Cross-restart durability is established only by comparing a pre-restart anchor to a post-restart snapshot.

## Access control

`!archivestatus` reuses the existing `audit_access.is_authorized()` allow-list. It is denied by default outside configured operator users/channels.

The command accepts no arbitrary path and cannot browse unrelated filesystem locations.

## Authority law

CAP-40E is observation only. It may not:

- write to the archive;
- write to alert history or telemetry;
- fetch market data;
- call GPT-5.6;
- alter candidate admission/cap;
- alter score/tier/capital/routing/cooldown/suppression;
- alter setup-family logic;
- alter scan cadence or universe;
- alter real-4H authority;
- certify persistence from one observation.

## Railway validation workflow

After CAP-40E deploys:

1. wait for a completed universe scan;
2. run `!archivestatus` in an authorized operator channel;
3. save the oldest/latest scan-id anchor and byte counts;
4. restart/redeploy the Railway service without deleting persistent storage;
5. run `!archivestatus` again;
6. verify the prior anchor is still present and archive bytes did not reset;
7. allow another completed universe scan;
8. run `!archivestatus` again and verify the latest anchor/bytes advance;
9. confirm alert history and normal scanner behavior remain intact.

If the pre-restart anchor disappears, CAP-40C/R4H-3C must be classified **NOT SAFELY ACCRUING** until Railway durable storage is corrected. Missing scan-time evidence must never be reconstructed from hindsight.

## Production invariants

CAP-40E does not change:

- universe: 814 symbols;
- cadence: 15 minutes;
- GPT-5.6 candidate cap: 30;
- Phase-14V trace cap: 9,000;
- SNIPE/STARTER/NEAR_ENTRY thresholds;
- Discord trade-alert routing;
- cooldown/dedup rules;
- real 4H `SHADOW_EVIDENCE_ONLY` authority.
