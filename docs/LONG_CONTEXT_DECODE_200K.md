# 200K c1 cold/warm decode screen

**Historical protocol/results.** New benchmark acceptance follows
[BENCHMARK_POLICY.md](BENCHMARK_POLICY.md); old zero-queue requirements below
do not govern new capacity-first runs. Original results remain unchanged.

**Status:** the operator approved this baseline screen on 2026-10-15, following
the 100K c1 decode screen. Both the cold and conditional warm invocations and
their post-traffic gates passed. This approval covered only these 200K c1 decode
invocations, not a retry, higher concurrency, candidate, or server change.

## Approved scope

- Preserved `baseline` profile only; unchanged effective settings, DP1, c1.
- Exactly **200,000 input tokens**, exactly **512 forced output tokens**, decode
  mode, and three measured serial rounds for each cache state.
- First: cold, no warmups. Then, conditional on passing cold and its audit: warm
  with **two explicit sequential unforced warmup passes** for the same prompt,
  followed by three timed requests. Warmups are not timed samples.
- At most three cold requests and five warm requests (two warmups + three timed).
  No retrieval check, concurrency increase, retry, cache flush, or progression to
  260K/near-limit decode.
- Fresh token-slot budget: `200,000 + 512 = 200,512` slots, about **12.63%** of the
  previously observed 1,587,968-slot shared pool. Recompute from current capacity;
  this arithmetic does not guarantee against hybrid-state exhaustion or OOM.
- Record cold cache hits as observed. For warm timing require at least **180,000
  cached tokens (90%) per timed request**; do not add warmups or relax this
  threshold after a failure.

## Preflight, sequencing, and stop conditions

Before cold, run offline setup validation and capture a fresh read-only inventory.
Verify readiness, baseline profile/configuration, DP1, effective input/context
limits, unchanged container/image/argv/start identity and cached-model metadata,
healthy host/container GPU queries, zero running/waiting loads, recent access records
with no unrelated inference routes, and the fresh budget. Explicitly account for
preflight GETs. Both `--execute` and `--confirm-idle` are required.

Use only the strict `tests/benchmark.py` path. Any sampled waiting fails that
invocation; do not reinterpret prefill waiting. Stop on request failure, output/token
mismatch, failed warm-cache threshold, missing/stale/conflicting telemetry,
queueing, retraction, unexpected traffic, configuration/identity drift, or inability
to establish idle. Preserve partial evidence; do not retry.

After cold, audit exactly three successful `/generate` requests, no other inference
routes, unchanged configuration/identity, and fresh idle loads. Only then run a
separate between-run traffic/idle check and consider the approved warm invocation.
If cold or its audit fails, do **not** run warm. Repeat the post-traffic audit after
warm. Submitted requests may remain in flight after a client error; the harness does
not implicitly cancel them.

## Approved commands — conditional, one invocation each

```bash
python3 -B tests/benchmark.py --label baseline-200k-c1-cold-decode \
  --profile baseline --mode decode --cache cold --concurrency 1 \
  --prompt-tokens 200000 --output-tokens 512 --rounds 3 \
  --execute --confirm-idle

python3 -B tests/benchmark.py --label baseline-200k-c1-warm-decode-passes2 \
  --profile baseline --mode decode --cache warm --warmup-passes 2 \
  --concurrency 1 --prompt-tokens 200000 --output-tokens 512 --rounds 3 \
  --execute --confirm-idle
```

The warm invocation is conditional on the cold-stage gates. This is a small c1
decode screen, not production/tail-latency qualification or authorization for
higher concurrency or 260K decode.

## Recorded result

Fresh setup validation, inventory, configuration/container/model-metadata
comparison, GPU queries, traffic, idle state, and budget passed before cold. The
budget was **200,512 / 1,587,968 slots (12.63%)**. After cold, the post-traffic
audit matched exactly three successful `/generate` requests, no other inference
routes, and idle loads. The separate between-run check found only its own
`/v1/loads` GET and another idle sample before warm.

| Cache | Timed requests | Median aggregate tok/s | Median TTFT | Median end-to-end latency | Cached tokens per timed request |
|---|---:|---:|---:|---:|---|
| Cold | 3 | 53.32 | 7.734 s | 9.602 s | 0 |
| Warm (2 warmup passes) | 3 | 236.52 | 0.288 s | 2.164 s | 199,936 / 200,000 each |

All timed requests used exactly 200,000 input and 512 output tokens, with zero
retractions. Sampled peak running was 1; waiting and retracted peaks were 0. The
two unforced warmups reported 0 then 196,608 cached tokens. p95 is unavailable at
three samples. Estimated median TPOT was **3.73 ms cold / 3.65 ms warm**; the large
warm aggregate-rate/TTFT change primarily reflects cached prefill, not a standalone
decode-kernel speedup.

The final audits matched exactly three cold and five warm successful `/generate`
requests, with no other inference routes, and confirmed idle loads and unchanged
configuration/identity/model metadata. They recorded 93 cold and 57 warm timestamped
non-access stderr lines. No error/warning/exception markers were detected; these
were interleaved with expected load-monitor, server-info, and generation records.
Raw logs were not retained. See the [preflight](../evidence/baseline-200k-c1-decode-preflight-20261015T144106.241195Z.json),
[cold report](../evidence/baseline-200k-c1-cold-decode-20261015T144110.873352Z.json),
[cold audit](../evidence/baseline-200k-c1-cold-decode-post-traffic-20261015T144223.017488Z.json),
[between-run check](../evidence/baseline-200k-c1-warm-between-run-check-20261015T144236.468801Z.json),
[warm report](../evidence/baseline-200k-c1-warm-decode-passes2-20261015T144239.473022Z.json),
and [warm audit](../evidence/baseline-200k-c1-warm-decode-post-traffic-20261015T144331.196176Z.json).

This is a small c1 screen, not production or tail-latency qualification. No 260K
decode or higher-concurrency test was run or authorized by this result.
