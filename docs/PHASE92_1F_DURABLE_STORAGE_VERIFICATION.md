# Phase 92-1F — Durable Storage Verification

Status: engineering implementation complete; live Railway persistence receipt required
Authority: measurement/audit only
Strategy authority: ZERO
Capital authority: ZERO
Tier authority: ZERO

## Purpose

The Phase 92 commercial-evidence store must survive process restart/redeploy without silently replacing or losing scan-time evidence. This checkpoint verifies the repository-side storage contract and provides an operator-only probe for the Railway Volume persistence test.

The commercial store remains separate from:

- `.state/alert_history.json` operational dedup/cooldown state;
- `.state/research_archive/` bounded research evidence.

The repository does not attempt to infer Railway durability from a local filesystem. A single successful read is not a durability proof.

## Repository contract

The configured commercial root is:

```text
.state/signal_outcomes/
    events/YYYY-MM-DD.jsonl
    outcomes/YYYY-MM-DD.jsonl
    health/durability_probes.jsonl
```

The event ledger is append-oriented and already uses `fsync` after each successful append. Phase 92-1F adds a separate append-only health probe file; the probe never writes event or outcome partitions and is never consulted by scanner judgment.

Read paths are corruption-tolerant: malformed lines are counted and isolated rather than causing the readable records to disappear. Duplicate IDs are reported rather than silently deduplicated out of history.

## Railway Volume contract

Railway Volumes are the required durable filesystem mechanism for data that must survive deployments/restarts. Because the application writes the configured relative path `.state/signal_outcomes`, the production Volume must cover the application's `/app/.state` path (or an equivalent mount that contains the configured absolute storage path).

At runtime Railway exposes `RAILWAY_VOLUME_NAME` and `RAILWAY_VOLUME_MOUNT_PATH`. The Phase 92-1F storage verifier reports these values and classifies alignment as:

- `ALIGNED` — configured commercial root is under the mounted Volume;
- `MISALIGNED` — a Volume mount is present but does not contain the commercial root;
- `UNVERIFIED` — the runtime does not expose a Volume mount path.

`UNVERIFIED` is never upgraded to `ALIGNED` by inference.

## Controlled persistence test

Run this on the production Railway service after a green deployment:

### 1. Verify the mount and create a pre-restart anchor

```bash
python scripts/verify_signal_outcome_storage.py
python scripts/verify_signal_outcome_storage.py --write phase92-1f-pre-restart-YYYYMMDD
```

Record:

- `probe_id`;
- `probe_sha256`;
- `RAILWAY_VOLUME_NAME`;
- `RAILWAY_VOLUME_MOUNT_PATH`;
- configured ledger path;
- `mount_alignment`.

The required pre-restart state is `mount_alignment=ALIGNED`.

### 2. Restart without rebuilding

Use the Railway service restart operation. The purpose is to test process/container restart against the same deployment and mounted Volume.

### 3. Verify the exact anchor

```bash
python scripts/verify_signal_outcome_storage.py --check phase92-1f-pre-restart-YYYYMMDD
```

Required result:

```text
status=PRESENT
match_count=1
mount_alignment=ALIGNED
```

### 4. Redeploy and verify again

After a normal green redeploy, repeat the exact `--check` command. The same anchor must still be present.

### 5. Append a second anchor

```bash
python scripts/verify_signal_outcome_storage.py --write phase92-1f-post-redeploy-YYYYMMDD
```

The original anchor must remain. The probe file is append-only; a second anchor must increase history rather than replace the first.

## Corruption test

The repository test suite proves that a malformed probe line or event line is isolated and counted without destroying valid records. A controlled production corruption test is **not** required merely to satisfy the runtime checkpoint; it must never be performed destructively against the live commercial ledger.

If production evidence ever reports malformed records, preserve the original file and classify the issue as a storage/reconciliation incident before attempting recovery.

## Acceptance gate

Phase 92-1F passes only when all of the following are true:

1. repository storage tests pass;
2. compile and full Production Tests CI pass;
3. commercial root is distinct from operational state and research archive;
4. event/probe writes are append-only and idempotent by identity;
5. malformed records are isolated and reported;
6. duplicate IDs are detected without deleting raw history;
7. a fresh Python process can reconstruct the prior anchor;
8. production Railway reports an actual Volume mount covering the commercial root;
9. the exact pre-restart anchor survives restart;
10. the exact anchor survives redeploy;
11. scanner/tiering/capital/routing behavior is unchanged;
12. no storage-health failure can create, suppress, downgrade, or promote an alert.

Repository CI can prove items 1–7 and the strategy isolation contract. Only the live Railway procedure can prove items 8–10.

## Non-goals

Phase 92-1F does **not**:

- settle future outcomes;
- call market-data providers;
- modify the scheduler;
- change Discord delivery;
- alter tiering or capital policy;
- promote real 4H authority;
- create performance statistics;
- prune commercial evidence;
- treat one health snapshot as durability proof.

Those belong to later Phase 92 checkpoints.
