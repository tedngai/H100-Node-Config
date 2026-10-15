# Scheduling-aware 32K screening, protocol v1

**Historical protocol:** retained for reproducing old results. New general tests
use [capacity-first policy](BENCHMARK_POLICY.md), without a fixed prefill-wait cap.
The references below to the old default zero-queue rule describe historical runs.

This explicitly separate protocol follows the approved c2 prefill diagnostic.
It **does not change** `benchmark.py`'s zero-queue rule or the recorded strict c2
failure. It uses `tests/scheduled_benchmark.py` and the monitored round engine shared
with `prefill_diagnostic.py`; that diagnostic's CLI remains fixed at c2/cold/one
round/five seconds.

## Bounded invocation

- Preserved baseline configuration only, DP1; no deployment or candidate support.
- One chosen client concurrency **2, 4 or 6**, one cache state, **three timed rounds**.
- Each request uses exactly **32,768 input / 512 forced output tokens**.
- Cold rounds use distinct early namespaces and require zero reported cached tokens.
- Warm uses two explicit sequential unforced passes per independent prompt, followed
  by three concurrent timed rounds with ≥90% reported prefix reuse on every request.
  Warmup timings/results are retained but never included in the measured sample set.
- Max requests: `3 × concurrency` cold, `5 × concurrency` warm. No automatic
  invocation matrix, retry, extra warmup, cache flush or server change.
- Both live confirmation flags, an approved idle window, inventory/traffic review,
  and a fresh per-round token budget are required. Advance c2 → c4 → c6 manually
  only after lower-load cases and access-record audits pass. Larger contexts and
  configuration experiments are outside this stage.

## Queue policy, declared before live measurements

Initial waiting may be observed within a fixed **eight-second window from the
first request submission of that phase**. This common cap is an experimental stop
bound, not a performance target, admission guarantee or exact waiting duration.
The original diagnostic keeps its separate five-second cap.

When queueing is observed, all queued GET intervals must finish before all requests
have produced first visible text, and both cumulative prefill counters must show
progress while waiting. Late/overlapping reads or missing progress are inconclusive
and stop further rounds; they are not silently ignored as snapshot lag.

The shared engine requires fresh single-DP0 telemetry, monotonic cumulative counters,
no retractions, no reported running+waiting count above the submitted client count,
exact token accounting, unchanged healthy settings and a newer idle publication
after every phase. It uses a 30-second client request timeout and samples at 0.1 s.
Missing/stale/reset/conflicting telemetry fails the phase. Published timestamps
are deduplicated, never summed as TP replicas. Running-batch count excludes some
prefill activity; neither it nor client concurrency establishes total active GPU
concurrency. Known in-flight requests cannot be unsubmitted on a monitor signal;
there is no implicit cancellation, restart or further submission after a failed phase.

## Timing and interpretation

Aggregate output tokens/s uses the wall time of one concurrent submitted round,
including its prefill/waiting, through completed streams. CPU prompt building,
warmup, monitoring setup, post-round idle drain and configuration checks are outside
that timed interval. Per-request throughput and text TTFT use the existing stream
client clock. All phases, observations and failed/partial results are preserved.

Reports use kind **`scheduling-aware-benchmark`**, distinct from `benchmark` and
`prefill-queue-diagnostic`. `passed` means these screening checks passed;
`no_queue_qualified` and `production_qualified` remain false. Queue peaks,
classification and `strict_no_queue_observed` are retained, not hidden. Three
rounds are not tail-latency qualification. Compare only matched instances of this
protocol, not a mixed table of strict/diagnostic/scheduling-aware results.

Access-record counts are checked between invocations; shared-address attribution
and sampled observations cannot exclude all interference. No raw logs or endpoint
dumps are retained. The pre/post-reboot checkpoint metadata caveat still applies.
