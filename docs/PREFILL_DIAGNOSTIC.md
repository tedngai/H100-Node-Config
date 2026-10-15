# Separate bounded prefill-queue diagnostic

**Historical protocol:** retained for reproducing old observations. New benchmark
acceptance is [capacity-first](BENCHMARK_POLICY.md); references below to the old
default strict queue rule do not apply to new capacity tests.

This is an observation protocol, **not** a no-queue throughput qualification or
permission to modify SGLang. It does not change `benchmark.py`'s strict queue rule
or reclassify the failed 32K c2 cold report.

## Fixed live scope

- Preserved baseline profile only; ready DP1 server, unchanged effective settings.
- Exactly one cold round: **two independent 32,768-token inputs**, each generating
  exactly **512 output tokens**. No warmup, subsequent round, retry or higher load.
- Both `--execute` and `--confirm-idle` required in an approved quiet window.
- Fresh token-budget check, read-only identity/model-metadata inventory and traffic
  check before execution. Idle is checked both before and after CPU tokenization.
- Existing CPU-only cached tokenizer; no flush, container change or metrics toggle.

## Observations and diagnostic guards

The diagnostic samples the one DP0 `/v1/loads` row at a 0.1 s client interval.
It retains allowlisted running/waiting/retraction counts, published timestamps and
cumulative `total_prefill_uncached_tokens` / `total_prefill_busy_us` counters.
Required missing/invalid counters are unavailable, not zero, and block inference.
Published snapshots must be fresh (host/container wall-clock age between -1 and
2 seconds). Each request's first visible text is recorded on the client monotonic
clock by an optional stream observer; normal benchmark timing is unchanged.

The separate protocol permits observing initial waiting within **five seconds of
the first submission**. This is an observation bound, not a production SLA or an
exact queue-duration estimate. A waiting observation later than that, reported
running+waiting above two, any retraction, missing/stale/reset/conflicting telemetry,
request/accounting failure, drift or failure to establish a newer idle snapshot
fails the diagnostic. Requests have a 30-second client timeout. There are no further
submissions once the two in-flight requests have started; the monitor cannot undo
those submissions. No implicit cancellation/restart is attempted. A client timeout
does not prove server cancellation; verify pending requests before any retry.

Queue observations are classified as consistent with transient prefill waiting
only if all queued GET observations finish before both requests have produced
their first visible text and both cumulative prefill counters progressed during
waiting. Overlapping/late reads or absent progress remain inconclusive. Repeated
published timestamps are deduplicated for counter/unique-snapshot analysis, but
late repeated reads still prevent confident phase attribution. Counter deltas are
one DP0 source, never a sum of TP replicas. Queue observations are not queue-event
counts, and running-batch count zero is not proof that no prefill is on the GPU.

A newer idle publication is required after completion, followed by read-only
configuration and traffic checks. All evidence, including failure/partial results,
is written exclusively to timestamped files. No raw logs or endpoint dumps are saved.

The report kind is `prefill-queue-diagnostic`, always `performance_qualified: false`.
`passed` refers only to this bounded diagnostic protocol. Temporal association is
not an internal scheduler trace, proof of the exact bottleneck or permission to
resume c4/c6/long-context tests. A scheduling-aware performance protocol would need
separate review/approval. The existing strict no-queue failure remains failed.
