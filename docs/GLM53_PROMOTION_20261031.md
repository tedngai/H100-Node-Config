# GLM production promotion — 2026-10-31

**Serving production with explicit operator approval.** Promotion completed at
14:29:43 UTC, after disclosure of the pre-promotion single-pair 1M timing concern.
This is a monitored deployment decision, not a claim of production-tail or
sustained-load qualification.

## Selected service

| Item | Value |
|---|---|
| Container | `tensorfold-glm53-candidate-789e8f3bdfa2` (name/identity retained, role now production) |
| Image | `tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100` |
| Image ID | `sha256:09cb4a76ca5ee2080c3f50bca7985c904c5b48f741f61940ffa734d35ffe179c` |
| Recipe | `bf5f94523a8251029cedae86bf61f8ce37fac218`, hash `789e8f3bdfa2`, 123 patches |
| Endpoint / alias | `http://127.0.0.1:8011/v1` / `pratt-medium` |
| Restart policy | `unless-stopped` (old GLM and Qwen: stopped, `no`) |
| Context / shared pool | 1,048,576 / 4,345,856 tokens |
| Parallelism | TP4, four streams, H100/NVLink/NCCL |
| Model / drafter | Same pinned EXL3 model and DFlash2 revisions as before |
| Precision / memory | q4 dense, fp8 KV, 22.5 GiB pool cap / 5 GiB reserve |
| Promotion readiness | 150.77 s |

The tested container was started, not recreated or renamed. The old GLM
container/image remain the primary rollback; Qwen remains a secondary fallback.
No model downloads, image rebuilds, optional tuning or deletions were performed.
The production authority is [`configs/glm53-production.json`](../configs/glm53-production.json),
not the older external project's launch config/scripts. GLM harness defaults now
follow that profile for the selected container and rank-log audits.

Promotion smoke passed chat, separated reasoning, synthetic tool call and vision.
All six additional agent/API checks passed: Anthropic streaming usage, Responses,
quoted markers in structured output, tool-result continuation, cached multi-turn
continuation and cancellation. Synthetic tools are never executed.

Evidence:
- `evidence/glm53-production-promotion-20261031T142701835459Z.json`
- `evidence/glm53-promoted-smoke-20261031T142934.658258Z.json`
- `evidence/glm53-promoted-agent-api-20261031T142936.578270Z.json`

The promotion event's profile-update-pending flag records the stage at which it
was captured; the subsequent committed production JSON completes that update.

## Post-promotion benchmarks

Each invocation is bounded, sequential, explicitly approved and
requires idle confirmation. Unique cold prompts and verified warm cache reuse
are reported separately. Results and failures are timestamped under `evidence/`.
No unrelated inference should be sent during measurement.

Aggregate throughput means actual output tokens divided by client wall time,
including prefill/TTFT. Per-request decode estimates exclude TTFT but are not
kernel-level throughput; never sum duplicate TP metrics. Sampled free HBM is
per GPU and is not a guarantee against shorter transient peaks.

### Short decode and sampling — complete

~1,024 input / 256 forced output tokens per request, three rounds per workload.
Temperature 0 for greedy; temperature 1 / top-p 0.95 for sampled. Warm measured
requests each passed the >=90% reported prompt-cache reuse guard.

| Workload | Samples | Median aggregate tok/s | Median decode estimate tok/s/request | TTFT p50 s | Evidence filename |
|---|---:|---:|---:|---:|---|
| c1 cold greedy | 3 | 180.176 | 202.128 | 0.1519 | `glm53-promoted-c1-cold-20261031T143050.718244Z.json` |
| c2 cold greedy | 6 | 241.161 | 138.814 | 0.2322 | `glm53-promoted-c2-cold-20261031T143055.329417Z.json` |
| c4 cold greedy | 12 | 372.230 | 118.914 | 0.4068 | `glm53-promoted-c4-cold-20261031T143102.042852Z.json` |
| c1 warm greedy | 3 | 220.727 | 222.414 | 0.0081 | `glm53-promoted-c1-warm-20261031T143111.076330Z.json` |
| c2 warm greedy | 6 | 301.265 | 162.723 | 0.0203 | `glm53-promoted-c2-warm-20261031T143114.923727Z.json` |
| c4 warm greedy | 12 | 465.444 | 125.454 | 0.0545 | `glm53-promoted-c4-warm-20261031T143120.633385Z.json` |
| c1 cold sampled | 3 | 172.817 | 192.855 | 0.1533 | `glm53-promoted-c1-sampled-20261031T143128.208588Z.json` |
| c4 cold sampled | 12 | 357.332 | 109.942 | 0.4041 | `glm53-promoted-c4-sampled-20261031T143132.919558Z.json` |

All eight reports are under `evidence/`; all passed with the exact promoted image,
expected request-counter deltas and no observed OOM. Small sample counts are
bounded screens, not reliable tail distributions or statistically established
cross-build speedups. Do not combine workloads to claim a larger p95 sample size.

### Long-context and mixed load

Post-promotion long-context retrieval/decode, two 1M requests and mixed streaming
are running sequentially; no results are claimed here until those reports finish.

## Qualification / accepted caveat

Pre-promotion validation passed 17 CPU checks, bounded live interface/API checks,
995,844-token retrieval, mixed 200K-prefill/4,096-token streaming, cancellation,
and a real same-container restart with unchanged engine source. One matched
pre-promotion 1M pair measured 186.467 s TTFT new versus 175.308 s old (+6.37%).
That single-pair observation remains in the
[pre-promotion report](GLM53_UPDATE_VALIDATION.md); cause and significance are
not established. Fresh production runs do not erase it.

No sustained-load, overload/fairness, p95/p99, four-concurrent-1M, workload-wide
coding/vision quality, external-gateway or host-reboot qualification is claimed.
Original baseline and historical evidence remain unchanged.
