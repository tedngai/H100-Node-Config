# Measurement definitions and limits

Acceptance rules are now [capacity-first](BENCHMARK_POLICY.md): work completion,
runtime health, performance observations and telemetry completeness are separate.
Queueing/retractions and low sampled free memory no longer fail default capacity
tests. Historical reports and specialized fixed protocols retain their old rules.

- **Per-request end-to-end tokens/s:** final actual completion-token count divided
  by client time from request submission through stream completion. Includes
  queueing, prefill and network overhead; not pure decode-kernel speed.
- **Aggregate tokens/s:** total actual completion tokens in one concurrent round
  divided by the client wall time for that round. Never average server-native
  throughput fields or multiply a single request's speed by concurrency.
- **TTFT:** time until the first non-empty generated text event is received. Empty
  metadata events do not count. A decoded text event can contain several tokens,
  so this is client-visible text TTFT, not the first internal model-token timestamp.
- **Average TPOT estimate:** first-to-last event with an increased completion-token
  count, divided by the token-count increase between those events. This accounts
  for multi-token first bursts and invisible special tokens after visible text
  stops. Speculative bursts and buffered events still make this an estimate, not
  a per-token interval distribution. The original text-based timing probe is
  retained but excluded from matched comparisons.
- **Per-request decode speed estimate:** invert each request's average TPOT estimate,
  then take the median of those request speeds. This excludes the interval before
  the first counted token event; stream buffering and speculative bursts still
  apply. Do not divide aggregate throughput by concurrency or invert the median
  TPOT (not generally the same statistic). This is not pure decode-kernel speed.
- **Cold:** early per-run/per-round/per-session unique markers prevent reuse of
  long document prefixes. Short role/template prefixes can still be cached; use
  actual reported cache-hit counts to interpret a result. No cache flush is sent.
- **Warm:** sequential unforced warmup on each exact prompt, then timed concurrent
  runs on those prompts. Require reported cache hits for at least 90% of input on
  every measured request. Warmup time/results are retained and excluded from timings.
  Retrieval-mode warmups also require the expected codes. Decode warmups validate
  token accounting and runtime behavior, not recall; retrieval is checked separately.
  Default is one pass per prompt. Explicit `--warmup-passes 2` or `3` permits a
  bounded diagnostic for hybrid branch-checkpoint materialization; there is no
  adaptive retry loop. Every pass is recorded with zero-based pass/prompt indices.
  Extra passes never relax measured cache-hit checks and require `--cache warm`.
  Compare warm results only with the same explicit warmup-pass policy.
- **Inputs:** model chat template, thinking disabled for native speed/retrieval
  tests, seeded diverse natural-text records, and retrieval codes at the beginning,
  middle and end. The separately encoded template parts are submitted as exact
  token IDs, not retokenized text. Assert actual reported input count equals target.
  Record each prompt hash, run namespace and seed; do not save massive token arrays.
- **Reasoning:** the OpenAI smoke check separately enables thinking and verifies
  a nonempty `reasoning_content` field with a completed, separated final answer.
- **Forced output:** decode mode requests a long technical explanation, sets
  `ignore_eos=True`, and checks exact output length. Its code-presence fields are
  not quality pass/fail criteria. Retrieval mode requests only the codes, allows
  normal termination, and requires all expected codes in the final answer.
- **Metrics:** the read-only `/v1/loads` endpoint exposes DP1 active/waiting counts
  even with Prometheus disabled in this build. The harness samples it without
  changing server settings, falling back to Prometheus only when enabled. Duplicate
  TP Prometheus series use maxima, never sums. Unavailable counters remain unknown.
  Client c6 alone is not proof of six active GPU requests. Sampled peaks are
  observations, not exhaustive concurrency traces, and short retrieval requests
  can finish between snapshot publications.
- **Traffic isolation:** refuse a non-idle initial load snapshot and stop later
  rounds if sampled active requests exceed benchmark client concurrency. That
  condition is sufficient to detect some interference, not all of it. Audit
  generation-request timestamps separately; unrelated traffic can occur without
  exceeding the benchmark's client count. Never block production clients implicitly.
- **Retractions:** report the sum of per-request retractions only when every
  request supplies that field. Missing data is `null`, not zero. Scheduler metric
  peaks, where present, are separate and not assumed to be per-run event totals.
- **Statistics:** three-round runs screen candidates, not production tails. p95 is
  omitted below 30 requests. Even 30 is a weak tail estimate; repeat longer runs
  during a separately approved window before drawing reliability conclusions.
- **Comparisons:** hold model, image, build overlays, tokenizer/template, workload
  seed, prompt/output lengths, cache state, client concurrency, warmup policy and
  mode constant. Namespaces vary to isolate long-prefix caches. Account for any
  changed automatic admission, graph allocation or state-pool sizes.
- **Failures:** retain partial output, exceptions, before/after configuration and
  timestamps. Unknown counters stay unknown, but missing performance telemetry is
  separate from a workload-completion verdict. A runtime failure remains a failure.

## Separate scheduling diagnostic

[`PREFILL_DIAGNOSTIC.md`](PREFILL_DIAGNOSTIC.md) specifies a fixed one-round 32K c2
legacy observation protocol. It predates the capacity-first policy and
records diagnostic results under a different report kind, always with
`performance_qualified: false`. First-text arrivals and load GET intervals share
the client monotonic clock; published timestamps deduplicate cumulative prefill
counters. Missing/stale/reset observations are not converted to zero or a pass.
Transient waiting plus prefill progress is a temporal association, not proof of
the internal scheduler cause or permission to advance a performance matrix.

## Separate scheduling-aware screening

[`SCHEDULED_SCREENING.md`](SCHEDULED_SCREENING.md) specifies bounded 32K c2/c4/c6
screening with a fixed eight-second initial-prefill observation cap. It uses report
kind `scheduling-aware-benchmark`, never silently relabels strict no-queue failures,
and retains queue peaks and phase classification. Round timing includes waiting
and prefill but excludes CPU tokenization, warmups and post-round drain/checks.
Compare only matched scheduling-aware runs; normal `summarize.py` intentionally
does not merge their different report kind into its benchmark table. The table
now labels capacity versus explicit/historical no-queue policies separately.

These tests do not measure coding-task quality, fairness, sustained production
traffic, cache restoration after host offload, or external gateway routing.
