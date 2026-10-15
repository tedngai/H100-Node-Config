# 260K c1 cold retrieval near-limit screen

**Historical protocol/results.** New benchmark acceptance follows
[BENCHMARK_POLICY.md](BENCHMARK_POLICY.md); old zero-queue requirements below
do not govern new capacity-first runs. Original results remain unchanged.

**Status:** the operator approved one exact attempt on 2026-10-15 after the
eight-hour quiet-window check. The fresh preflight and one benchmark invocation
passed. This is a single-session synthetic retrieval screen on the unchanged
baseline; it does not authorize a retry, higher concurrency, candidate, or
configuration change.

## Approved scope

- Preserved `baseline` profile only; unchanged effective settings, DP1, c1.
- Exactly **260,000 input tokens**, a maximum of **1,024 output tokens**, cold
  synthetic retrieval, and **three serial rounds** (at most three inference
  requests). No warmup, concurrent request, decode-throughput phase, retry, cache
  flush, or automatic progression.
- Use the existing CPU-only prompt builder and unique round namespaces. Each
  response must recover the three synthetic codes placed near the beginning,
  middle, and end of its prompt. Output terminates normally; 1,024 is a cap.
- Fresh token-slot budget: `1 × (260,000 + 1,024) = 261,024` slots, approximately
  **16.44%** of the previously observed 1,587,968-slot shared pool. The request is
  within the captured 262,144-token context and 262,138-token input limit. This
  arithmetic does not guarantee hybrid-state headroom, avoid OOM, or establish
  runtime safety near the limit.

## Fresh preflight and stop conditions

The eight-hour quiet-window check is recorded in
[`quiet-window-check-20261015T122020.551986Z.json`](../evidence/quiet-window-check-20261015T122020.551986Z.json).
Immediately before execution, make a fresh read-only inventory and verify:

- the original container/image/argv/start identity and effective configuration
  still match `configs/baseline.json` and the latest post-reboot checkpoint;
- current cached-model metadata matches the latest checkpoint (metadata does not
  prove which weights the already-running process loaded);
- host and container GPU queries are healthy, server readiness is good, and a
  fresh `/v1/loads` publication shows zero running and waiting requests;
- recent access records since the last quiet-window checkpoint show no unrelated
  inference route; explicitly account for read-only preflight GETs;
- setup validation and the fresh token budget pass, and baseline evidence integrity
  remains valid.

Use only the existing strict `tests/benchmark.py` retrieval path. Any sampled
waiting request fails the invocation; do not reinterpret prefill waiting or switch
to scheduling-aware screening. Stop on a request/recall failure, token mismatch or
truncation, queueing, retraction, missing/stale/conflicting telemetry, unexpected
traffic or active count, GPU/server/configuration drift, or inability to establish
idle afterward. Do not submit later rounds after a failure or retry. Submitted work
may remain in flight after a client error; there is no implicit cancellation.

After a successful invocation, audit access records to match exactly three
successful `/generate` requests to the benchmark report, with no unrelated
inference routes. Verify unchanged identity/configuration and a fresh idle load
sample. Preserve all failed or partial evidence; do not overwrite existing files.

## Executed command — do not repeat

```bash
python3 -B tests/benchmark.py --label baseline-260k-c1-cold-retrieval \
  --profile baseline --mode retrieval --cache cold --concurrency 1 \
  --prompt-tokens 260000 --output-tokens 1024 --rounds 3 \
  --execute --confirm-idle
```

The approval covers one attempt of this exact scope only. A fresh preflight is
still mandatory; this protocol does not authorize execution if any gate fails.

## Recorded result

The fresh preflight passed: setup validation and baseline integrity, healthy host
and container GPU queries, unchanged effective configuration/container identity/
cached-model metadata, idle loads, and the fresh 90%-pool budget. The request budget
was **261,024 / 1,587,968 slots (16.44%)**. Two preliminary traffic-comparison
reports are preserved; their first pass mishandled Docker's split stdout/stderr and
the cutoff precision. The final preflight reconciled the exact read-only GET counts
and sent no inference before the approved run.

The benchmark completed all three serial requests. Every prompt was exactly
260,000 tokens; all three synthetic codes were recovered in all three responses.
Each response used 40 output tokens, with zero cached tokens and zero per-request
retractions. Sampled peak running was 1; sampled peak waiting and retracted counts
were 0. Median TTFT was **11.242 s**, median end-to-end latency **11.335 s**, and
the **3.53 output tok/s** summary is the rate for short 40-token retrieval answers,
not decode-throughput qualification. p95 is unavailable at three samples.

The final post-run audit matched exactly three successful `/generate` requests and
no other inference routes. It recorded zero running/waiting loads afterward;
configuration, container identity/start, and cached-model metadata were unchanged.
There were 101 timestamped non-access stderr log lines during the benchmark and
post-inventory interval. No error/warning/exception markers were detected; their
nearest access records were the expected load-monitor and server-info reads. Raw
logs were not retained. The initial conservative post-audit report is preserved;
the final audit reconciled routes and recorded the successful idle check.

Evidence: [benchmark](../evidence/baseline-260k-c1-cold-retrieval-20261015T124657.082330Z.json),
[preflight](../evidence/baseline-260k-c1-preflight-final-20261015T124651.694944Z.json),
[post-inventory](../evidence/baseline-260k-c1-posttest-20261015T124806.456330Z.json),
and [final post-traffic audit](../evidence/baseline-260k-c1-post-traffic-final-20261015T125047.503452Z.json).
This pass qualifies only this synthetic c1 retrieval screen. It does not qualify a
full 262K prompt, decode throughput, production behavior, or any higher load.

## Interpretation

This is a three-request synthetic retrieval check, not decode-throughput,
production, broad-recall, memory-safety-at-load, or tail-latency qualification.
Three samples are insufficient for p95. The prior 200K pass does not qualify 260K
runtime behavior, and the strict 32K c2 no-queue failure remains unchanged.
