# 100K c1 cold/warm decode screen

**Historical protocol/results.** New benchmark acceptance follows
[BENCHMARK_POLICY.md](BENCHMARK_POLICY.md); old zero-queue requirements below
do not govern new capacity-first runs. Original results remain unchanged.

**Status:** the operator approved this staged baseline screen on 2026-10-15. Both
the cold and conditional warm invocations passed their benchmark and post-traffic
gates. This approval covered only these 100K decode invocations, not 200K, higher
concurrency, candidates, retries, or server changes.

## Approved scope

- Preserved `baseline` profile only; unchanged effective settings, DP1, c1.
- Exactly **100,000 input tokens**, exactly **512 forced output tokens**, decode
  mode, and three measured serial rounds for each cache state.
- First: cold, no warmups. Then, only after review of the cold result and traffic
  checkpoint: warm with **two explicit sequential unforced warmup passes** for the
  same prompt, followed by three timed requests. Warmups are excluded from timing.
- At most three cold requests and five warm requests (two warmups + three timed).
  No retrieval-quality claim, concurrency increase, retry, cache flush, decode
  parameter change, or automatic progression to 200K.
- Fresh budget per client: `100,000 + 512 = 100,512` token slots, about **6.33%**
  of the previously observed 1,587,968-slot shared pool. The budget is not a runtime
  memory-safety guarantee.
- Cold cache does not guarantee zero cache hits. Record the actual cached-token
  counts. For warm timing, require at least **90,000 cached tokens (90%) on every
  timed request**; do not add warmups or relax this threshold after a failure.

## Preflight, sequencing, and stop conditions

Before the cold invocation, capture a fresh read-only inventory and setup
validation. Verify the baseline profile, readiness, DP1, input/context limits,
unchanged container/image/argv/start identity and cached-model metadata, healthy
host and container GPU queries, zero initial running/waiting loads, recent access
records with no unrelated inference routes, and the fresh budget. Account for
preflight GETs explicitly. Both `--execute` and `--confirm-idle` are mandatory.

Use only the strict `tests/benchmark.py` path. Any sampled waiting request fails
that invocation; do not reinterpret prefill waiting. Stop on failed warmup, request
failure, output/token mismatch, missing/stale/conflicting telemetry, queueing,
retraction, unexpected route/activity, configuration/identity drift, or inability
to establish idle afterward. Preserve partial evidence and do not retry.

After cold, audit access logs against its three `/generate` requests, check for no
other inference routes, verify unchanged configuration/identity and fresh idle
loads, then decide whether to submit the approved warm invocation. Repeat the
traffic/idle checks after warm. If the cold stage or audit fails, **do not run warm**.
Submitted work may remain in flight after a client error; the harness does not
implicitly cancel it.

## Approved commands — one invocation each

```bash
python3 -B tests/benchmark.py --label baseline-100k-c1-cold-decode \
  --profile baseline --mode decode --cache cold --concurrency 1 \
  --prompt-tokens 100000 --output-tokens 512 --rounds 3 \
  --execute --confirm-idle

python3 -B tests/benchmark.py --label baseline-100k-c1-warm-decode-passes2 \
  --profile baseline --mode decode --cache warm --warmup-passes 2 \
  --concurrency 1 --prompt-tokens 100000 --output-tokens 512 --rounds 3 \
  --execute --confirm-idle
```

The warm command is conditional on the cold-stage gates above. These runs measure
decode behavior at one context/concurrency only; they do not qualify retrieval,
production quality, tails, 200K decode, or candidate settings.

## Recorded result

Fresh setup validation, inventory, configuration/container/model-metadata
comparison, GPU queries, budget, and traffic checks passed before the cold run.
After cold, the audit matched exactly three `/generate` requests, found no other
inference routes, and recorded zero running/waiting requests. The separate
between-run check found only its own `/v1/loads` GET and idle service before warm.
Both post-run inventories matched the unchanged baseline configuration and
container identity/start; cached-model metadata was unchanged.

| Cache | Timed requests | Median aggregate tok/s | Median TTFT | Median end-to-end latency | Cached tokens per timed request |
|---|---:|---:|---:|---:|---|
| Cold | 3 | 99.44 | 3.368 s | 5.148 s | 0 |
| Warm (2 warmup passes) | 3 | 243.75 | 0.242 s | 2.100 s | 99,968 / 100,000 each |

Every timed request used exactly 100,000 input and 512 output tokens, with zero
retractions. Sampled peak running was 1; waiting and retracted peaks were 0. The
two unforced warmups reported 0 then 99,968 cached tokens. p95 is unavailable with
three timed samples. The higher warm aggregate rate/lower TTFT primarily reflects
prefix-cache reuse; estimated median TPOT was about **3.50 ms cold / 3.64 ms warm**,
not evidence of a decode-kernel speedup.

The final audits matched exactly three cold and five warm `/generate` requests,
with no other inference routes, and confirmed idle loads. The cold audit recorded
57 and the warm audit 46 timestamped non-access stderr lines; no error/warning/
exception markers were detected, and these were interleaved with expected load,
server-info, and (warm) generation access records. Raw logs were not retained. An
initial conservative cold audit is preserved; the final route/idle reconciliation
passed. See the [cold report](../evidence/baseline-100k-c1-cold-decode-20261015T143114.453343Z.json),
[cold audit](../evidence/baseline-100k-c1-cold-decode-post-traffic-final-20261015T143305.625744Z.json),
[between-run check](../evidence/baseline-100k-c1-warm-between-run-check-20261015T143328.877219Z.json),
[warm report](../evidence/baseline-100k-c1-warm-decode-passes2-20261015T143336.993764Z.json),
and [warm audit](../evidence/baseline-100k-c1-warm-decode-post-traffic-20261015T143429.403552Z.json).

This is a small c1 screening comparison, not tail-latency, production, or 200K
qualification. Any 200K decode stage requires its own protocol, fresh checks, and
explicit approval.
