# 200K c1 cold retrieval baseline

**Status:** one 200K c1 cold retrieval attempt was separately approved and completed
on 2026-10-14. This is one conservative long-context retrieval check on the unchanged
baseline, not a throughput matrix or configuration experiment. Any repeat requires
separate approval.

## Proposed scope

- Preserved `baseline` profile only; DP1, unchanged effective settings, and c1.
- Exactly **200,000 input tokens**, at most **1,024 output tokens**, retrieval mode,
  cold namespace, and **three serial rounds** (maximum three inference requests).
- No warmup, concurrency increase, warm-cache case, decode-throughput run, retry,
  cache flush, candidate, deployment, or automatic progression to near-limit tests.
- Use the existing CPU-only prompt builder and distinct per-round namespaces. Require
  exact reported input-token count; record actual cached tokens. A cold namespace is
  not a guarantee of zero cache hits, and no cache flush is implied.
- Every response must recover the synthetic codes placed near the beginning, middle
  and end of the prompt. Output terminates normally; 1,024 is a cap, not a forced
  completion length.
- Fresh budget guard: `1 × (200,000 + 1,024) = 201,024` token slots, about **12.66%**
  of the currently recorded 1,587,968-token shared pool. The prompt plus output is
  within the recorded 262,144-token context, but this arithmetic is not a guarantee
  against hybrid-state exhaustion, OOM, or other runtime limits.

## Preflight and stop conditions

Execution requires separate explicit approval for this exact test and a current,
coordinated quiet window. Recapture read-only server/container/model/GPU inventory;
verify baseline profile, DP1, readiness, unchanged image/argv/container start and
effective settings, healthy GPU query, current model metadata, and zero initial
running/waiting loads. Review recent access records for unrelated traffic and compare
with the latest post-reboot checkpoint. Run offline setup validation and a fresh
token-budget check. A prior quiet-window confirmation or the successful 100K result
does not carry over.

Use only the existing **strict** `tests/benchmark.py` retrieval path. Any sampled
waiting request fails the invocation; do not reinterpret prefill waiting or switch to
the 32K scheduling-aware protocol. Stop on request/recall failure, token mismatch or
truncation, queueing, retraction, stale/missing/conflicting telemetry, unexpected
traffic/active count, health/configuration drift, or inability to establish idle
afterward. No subsequent round or retry after a failure; preserve partial evidence.
Submitted work may remain in flight after a client error, and the harness does not
implicitly cancel it.

After a successful invocation, require an access audit matching exactly three
successful `/generate` requests, no unrelated inference routes, unchanged
configuration/identity, and a fresh idle load sample. Any failed gate blocks the
test; a point-in-time idle sample alone is not proof of isolation.

## Interpretation

This is a synthetic functional retrieval screen at c1, not decode-throughput,
production, real-workload recall, memory-safety-at-load, or tail-latency qualification.
Three requests are too few for p95. The earlier strict 32K c2 no-queue failure
remains failed and is unaffected by a c1 retrieval result.

## Executed command — do not repeat without fresh approval

```bash
python3 -B tests/benchmark.py --label baseline-200k-c1-cold-retrieval \
  --profile baseline --mode retrieval --cache cold --concurrency 1 \
  --prompt-tokens 200000 --output-tokens 1024 --rounds 3 \
  --execute --confirm-idle
```

The command above completed once. All three requests passed the synthetic retrieval
check, with no sampled waiting or retractions; see the report in `docs/results.md`.
This result does not authorize 260K, higher concurrency, or candidate tests.
