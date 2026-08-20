# CAP-40 Candidate-Cap Decision

Status: deferred, evidence required.

Current production cap: **30 deep-analysis candidates per scan**.

Proposed next cap: **40**.

## Engineering position

Forty is the preferred next ceiling if it produces measurable incremental opportunity recall without compromising the 15-minute scan budget, API budget, or signal precision.

Moving 30 -> 40 increases maximum model calls by 33.3%. That is large enough to require evidence but small enough to be technically plausible.

## Why not change it inside a provider phase

A provider phase changes the model boundary only. Combining a capacity change with it would make any downstream difference impossible to attribute cleanly.

The setup-family compiler also needs to influence candidate admission before the cap study. Otherwise ten extra model calls can merely process ten more candidates ranked by the legacy admission bias.

## Existing measurement advantage

Phase 14V already records near-cut ranks 31-60 without extra deep-analysis calls. Therefore the scanner has a free shadow population for studying what the 30-candidate cutoff is excluding.

## CAP-40 acceptance test

After setup-family admission integration:

1. replay/inspect ranks 31-40 across a meaningful chronological sample;
2. measure how often they later qualify as legitimate NEAR_ENTRY, STARTER or SNIPE_IT under the same doctrine;
3. measure incremental target/stop/time-barrier outcomes;
4. measure model latency and complete scan duration at 30 vs 40;
5. measure API rate/cost impact;
6. verify quality/precision does not deteriorate merely because more candidates are reviewed.

Promote the cap to 40 only if incremental recall is real and operational headroom remains comfortable.

Do not use CAP-40 to compensate for weak candidate ranking.
