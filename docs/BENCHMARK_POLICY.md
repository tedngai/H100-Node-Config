# Benchmark policy — capacity first (v1)

This is the current policy for new benchmarks, approved by the operator on
2026-10-15. It supersedes earlier instructions requiring zero waiting, fixed
five/eight-second prefill windows, or a mandatory 3 GiB free-memory floor. Old
reports retain their original verdicts and policy; do not rewrite their evidence.

## The question we test

**Does the specified bounded workload complete without an observed OOM, with
correct token accounting and a healthy, unchanged server?** Queueing and NVML-free
memory are measurements, not automatic failure conditions. A successful run is
evidence for that workload only, not a universal concurrency or OOM-safety claim.

## Independent outcomes

| Dimension | Rule |
|---|---|
| Work completion | Every requested round/request completes; exact input and forced-output counts; retrieval recall only in retrieval mode |
| Runtime | No request error/timeout, stream error, observed OOM, restart, health failure or unexpected configuration change |
| Queue / latency | Report waiting, sampled running counts, TTFT, total latency and throughput; no arbitrary queue-duration or latency pass limit |
| Memory | Report per-device samples/minima and warnings below 3,072 MiB; no mandatory free-memory floor |
| Retractions | Report request totals when known and scheduler gauge peaks separately; warnings, not a failure if work completes |
| Measurement validity | Report missing telemetry as unknown and telemetry errors separately; never manufacture zeros or infer concurrency from client count |
| Isolation | Initially idle, coordinated approved window, no unrelated inference; exact traffic audit for memory candidates |
| Warm cache | A warm claim still requires at least 90% measured prefix reuse; failure is a mislabeled workload, not an OOM |

`passed` / `capacity_passed` mean the selected workload checks passed.
`oom_observed=false` means the available runtime audit found no OOM; without an
audit it is null. `telemetry_complete` and `warnings` are separate. Production
qualification is always false for these screens. A missing OOM audit prevents a
memory-candidate pass; missing performance counters do not turn completed work into
an OOM failure. Logged OOM markers are conservative signals, not an event total.

## What remains a gate

- Explicit approval and `--execute --confirm-idle`; each invocation is a bounded
  workload, not permission to advance an unattended matrix.
- Correct candidate profile/image/argv, ready DP1 server, no automatic truncation,
  per-request context limits, and the 90% shared-token-pool budget. These prevent
  accidental over-admission, not every possible allocation failure.
- Idle before inference and after each completed round. Allow up to five seconds
  for load publication/drain; do not reject a completed stream on one stale sample.
- Audit OOM markers, container restart/state and inference counts between rounds
  and at the end for memory candidates. Stop subsequent rounds on a real failure;
  retain completed and partial evidence. No automatic retry, cancellation, restart,
  flush, driver change, deployment, commit or publication.

Already submitted requests can remain in flight after a failure or timeout. This
policy accepts experimental OOM risk; monitoring does not guarantee prevention.
OOMKilled=false alone is insufficient: CUDA OOM can occur without Docker killing
the process, so request errors and aggregate runtime log markers are checked too.
Raw logs/environment/full inspect output are never saved.

## Implementation and controls

`tests/benchmark.py --policy capacity` is the default for new short/long,
cold/warm, decode/retrieval tests. The transport and timing code are retained;
the decision layer is rewritten in `tests/benchmark_policy.py`, with runtime
auditing in `tests/runtime_audit.py`.

- `--memory-warning-mib 3072`: advisory only; default.
- `--min-free-gpu-mib N`: optional explicit **hard** floor on memory-088 only.
  Omit it for the operator's completion/no-OOM screen.
- `--policy no-queue`: opt-in legacy zero-wait/retraction check, not default.
- `--arrival-stagger-seconds`: zero (default) preserves synchronized starts; a positive
  value schedules each client start at that interval within a round. Reports include
  planned and observed client-start offsets. The schedule span cannot exceed the request timeout.
- `--audit-container`: add runtime auditing for other profiles; automatic for
  memory-088. No service settings are changed to collect telemetry.

The fixed `prefill_diagnostic.py` and `scheduled_benchmark.py` tools are retained
as legacy protocol reproducers, not requirements for new capacity tests. Their
specialized criteria do not restrict `benchmark.py` capacity mode. Compare results
with matched policy/workload/cache state; do not mix old and new verdicts silently.

## Approved repeat

Unchanged memory-088, TP4/EP4/DP1, speculation and chunking unchanged. Six cold
100,000-input / 512-output requests, three rounds (18 total), after a fresh idle,
identity and traffic check. Queueing and low sampled free memory are advisory.
Do not advance to a longer input, different fraction or new topology automatically.

```bash
python3 -B tests/benchmark.py --label memory-088-c6-100k-capacity \
  --profile memory-088 --container sglang-qwen38-flash-next-088 \
  --policy capacity --mode decode --cache cold --concurrency 6 \
  --prompt-tokens 100000 --output-tokens 512 --rounds 3 \
  --execute --confirm-idle
```

## 100K repeat outcome

The approved repeat passed all three rounds (18 requests) with no observed OOM or
retractions. Queue peak 5 and GPU-free minimum 2,285 MiB are retained warnings;
sampled running reached six. Service remained unchanged and idle afterward.
See [results and evidence](MEMORY_FRACTION_FIRST.md). Final offline validation:
**94 tests passed**, including relaxed-policy, strict opt-in, OOM-stop, missing
telemetry and audit-error regression tests. The separately approved 200K stage is
recorded below.

## 200K stage outcome

The operator separately approved and completed c6 cold 200K/512 for three rounds.
All 18 requests completed without observed OOM/retractions; median aggregate was
62.72 tok/s. Waiting peaked at 5, sampled running reached 6, and minimum sampled
free memory was 2,265 MiB. See [the final audit](../evidence/memory-088-c6-200k-capacity-final-audit-20261015T173835.134422Z.json).
This does not authorize 230K/250K or a configuration change.

## 230K stage outcome

The operator then approved and completed c6 cold 230K/512 for three rounds. All 18
requests completed without observed OOM/retractions; median aggregate was 51.77 tok/s.
Waiting peaked at 5, sampled running reached 6, and minimum sampled free memory was
2,263 MiB. See [the final audit](../evidence/memory-088-c6-230k-capacity-final-audit-20261015T174546.906513Z.json).
250K and any configuration change remain separate approval gates.

## 250K stage outcome

The operator separately approved and completed c6 cold 250K/512 for three rounds.
All 18 requests completed without observed OOM/retractions; median aggregate was
46.03 tok/s. Waiting peaked at 5, sampled running reached 6, and minimum sampled
free memory was 1,629 MiB. See [the final audit](../evidence/memory-088-c6-250k-capacity-final-audit-20261015T175314.561930Z.json).
This is the 250K-input bounded screen only, not universal OOM-safety qualification.

## 250K / longer-output follow-up

The operator separately approved 250K cold inputs with 4,096 output tokens, three
rounds. All 18 requests completed without observed OOM/retractions; median aggregate
was 281.58 tok/s. Waiting peaked at 5, sampled running reached 6, and minimum sampled
free memory remained 1,629 MiB. See [the final audit](../evidence/memory-088-c6-250k-4k-capacity-final-audit-20261015T180948.379876Z.json).
At that stage, 256K and configuration changes were not authorized; the subsequently
approved 256K/512 screen is recorded next.

## 256K / 512-output near-guard outcome

The operator separately approved c6 cold 256,000-input / 512-output for three
rounds. All 18 requests completed with no observed OOM/retractions; median aggregate
was 44.57 tok/s. Waiting peaked at 5, sampled running reached 6, and minimum sampled
free memory was 1,629 MiB. The workload used 89.63% of the pool, leaving 6,393 slots
under the 90% guard. See [the final audit](../evidence/memory-088-c6-256k-capacity-final-audit-20261015T182137.670129Z.json).
This does not qualify longer output, universal OOM safety or production.

## Five-round 250K / 4096 outcome

The operator separately approved a five-round c6 cold 250K/4096 repeat (30
requests). All completed without observed OOM/retractions; median aggregate was
282.50 tok/s, initial latency p95 86.956 s, and minimum sampled free memory remained
1,629 MiB. The p95 is weak at n=30. See [the final audit](../evidence/memory-088-c6-250k-4k-5round-capacity-final-audit-20261015T183931.332380Z.json).

## Ten-round 250K / 4096 follow-up

The operator separately approved ten rounds (60 requests) of the same c6 cold
250K/4096 workload. All completed without observed OOM/retractions; median aggregate
was 282.60 tok/s, latency p95 88.551 s, and TTFT p95 63.769 s. Queueing peaked at
five waiting while sampled running reached six; minimum sampled free memory remained
1,629 MiB. The 60-sample p95 remains a limited estimate, not production-tail or
universal OOM-safety qualification. See [the final audit](../evidence/memory-088-c6-250k-4k-10round-capacity-final-audit-20261015T193456.102156Z.json).

## Ten-round staggered 250K / 4096 comparison

The operator separately approved ten rounds with six cold c6 requests started one
second apart. All 60 completed without observed OOM/retractions; measured client
starts matched the planned offsets 0–5 seconds within 0.4 ms. Median aggregate was
283.45 tok/s, initial latency p95 86.211 s and TTFT p95 58.604 s. Waiting peaked at
5, sampled running reached 6, and minimum sampled free memory remained 1,629 MiB.
Compared with the separate synchronized n=60 run, p50/p95 latency and TTFT were lower
in this run; this is descriptive only, not evidence of a causal or statistically
stable improvement. Both p95 estimates remain limited. See [the final audit](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-final-audit-20261015T200033.663353Z.json).
