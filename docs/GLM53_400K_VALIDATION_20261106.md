# GLM 400k / 8-stream bounded validation — 2026-11-06

**Result: bounded screening passed. Multi-day memory stability is not qualified.**
The serving image, limits, weights and container were unchanged during validation;
no restart, cache flush, allocator change or upgrade was performed.

Current configuration: `pratt-medium`, TensorFold v0.6.0 + recipe `789e8f3bdfa2`,
TP4 on four H100s, 400,000 tokens per request (prompt plus reply), maximum eight
streams and a 3,698,688-token shared pool. Container:
`tensorfold-glm53-400k-p8-20261106t165335`.

## Evidence and isolation

- [Derived summary, all passing-phase links and caveats](../evidence/glm53-400k8-validation-summary-20261106T190619529461Z.json).
- [Final isolated run and per-GPU trajectory](../evidence/glm53-400k8-validation-20261106T185123-20261106T185123.075163Z.json),
  18:51:23–19:06:19 UTC: requests_total 165 → 314, exactly **149** expected requests.
- Across **23 passing phases**, **212** completed requests, including eight warmups;
  two expected context refusals are additional. This is not the count for all
  interrupted attempts or unrelated traffic.
- Earlier [first](../evidence/glm53-400k8-validation-20261106T180802-20261106T180802.195141Z.json)
  and [second](../evidence/glm53-400k8-validation-20261106T181142-20261106T181142.587271Z.json)
  attempts stopped when the service did not return idle. Outside traffic was
  observed. Their passing isolated phases were retained; incomplete phases were
  rerun after isolation. Those controller reports count only passing phases in
  `requests_expected`, so their whole-run counter mismatch is **not** an exact
  outside-request count. No failed report was overwritten or relabeled as passing.

Existing guarded `tests/glm_smoke.py`, `tests/glm_benchmark.py` and
`tests/glm_mixed.py` were used with an approved isolated window, the current
profile, and `--execute --confirm-idle`. Every passing benchmark phase had the
expected request-counter delta. Missing telemetry is not treated as zero.

## Functional, concurrency and context checks

Chat, separated reasoning, a synthetic tool call and vision all passed. Tools
were not executed. Forced-output benchmarks checked generated-token accounting;
these checks do not establish general answer quality or drafted/serial equality.

| Workload | Measured requests | Median aggregate output tok/s | Median TTFT |
|---|---:|---:|---:|
| c1 greedy cold, ~1k input / 256 output | 3 | 180.19 | 0.152 s |
| c8 greedy cold, ~1k input / 512 output | 24 | 545.54 | 0.765 s |
| c8 greedy warm, ~8k input / 512 output | 24, plus 8 warmups | 626.70 | 0.152 s |
| c8 sampled cold, ~8k input / 256 output, T=1 / top-p=.95 | 24 | 147.04 | 5.995 s |

Aggregate throughput is output tokens divided by client round wall time, including
prefill. Rows have different input/output sizes and sampling; do not interpret
them as a matched scaling or temperature comparison. Eight actual decoders were
sampled in the c8 cold, warm and sampled checks. Warm requests reported 100% prompt
reuse. No p95 is claimed from these small per-workload samples.

- **Near-limit retrieval:** two prompt-cold requests of **389,979** and **390,158**
  tokens returned all three planted codes each. Median TTFT **57.863 s**; no cached
  prompt tokens. These are near-limit checks, not exact 400,000-token accepted
  requests or eight simultaneous near-limit contexts.
- **Boundary refusal:** 400,001 raw prompt tokens + one reply token received
  HTTP 400 / `context_length_exceeded`. So did a streaming request for 399,999
  prompt tokens + two reply tokens, before streaming. Normal generation passed
  immediately afterward; context is a total prompt-plus-reply budget.
- **Mixed prefill/decode:** 199,329 prompt tokens alongside 4,096 forced decode
  tokens; all retrieval codes found, actual overlap sampled. Long-request TTFT
  **34.048 s**, longest content-event gap **0.187 s**.

## Memory soak

The planned ten-minute soak ran **662.827 seconds** to finish its last bounded
batch: **15 eight-client batches / 120 requests**, alternating approximately 1k,
16k and 64k prompt targets, 512 forced output tokens each, greedy and sampled
settings alternating. All batches completed with exact traffic accounting.

Eight active decoders were observed in short and 16k batches. The 64k batches
sampled a peak of **four**, despite eight client requests. Configured/client
concurrency is not actual decoding concurrency.

| GPU | First soak post-batch idle used | Last soak post-batch idle used | Change | Minimum sampled free during final run |
|---|---:|---:|---:|---:|
| 0 | 70,876 MiB | 70,878 MiB | +2 MiB | 10,202 MiB |
| 1 | 69,610 MiB | 69,610 MiB | 0 | 11,470 MiB |
| 2 | 69,610 MiB | 69,610 MiB | 0 | 11,470 MiB |
| 3 | 69,610 MiB | 69,610 MiB | 0 | 11,470 MiB |

The preplanned tail after the first six batches contains nine idle observations
over **390.199 seconds**: used memory and fitted slopes were flat on all four
GPUs. Kept prompts varied and reached the configured count of 32. That is evidence
of a plateau **in this window**, not proof of a repaired leak or multi-day bounds.

The final run retained **425** combined health/GPU samples, **317** during the
soak, with no telemetry errors. Free-memory minima above use NVIDIA's reported
`memory.free`; child benchmark reports instead derive free as `total - used`,
which includes reserved memory and must not be substituted for these minima.
No sampled value guarantees the true transient minimum. TP memory is not summed.

No new OOM or explicit fatal rank-log markers were counted. The container
identity, image, start time and restart count were unchanged. Final health was
healthy/idle at 314 completed requests; context/pool/maximum streams unchanged.
Raw rank logs were not saved in this repository.

## Qualification boundary

This supports normal operation at the selected settings with continued
observation. It does **not** qualify multi-day stability, a fix for long-run
memory growth, eight concurrent 400k requests, exhaustive output quality,
drafted/serial equivalence, client gateways, host reboot recovery or production
tail latency. The original 1M/4-stream benchmarks remain historical.
