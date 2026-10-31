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

### Long-context retrieval — complete

Cold prompt cache, 256-token reply budget, temperature 0. All three requested
codes were recovered in every request; reported cached input tokens were zero.
The installed/compiled kernel cache from prior validation was reused: "cold"
does not mean first-use kernel compilation or a newly booted GPU.

| Target | Actual prompt range | Requests | TTFT median s | Median end-to-end aggregate tok/s | Evidence filename |
|---|---:|---:|---:|---:|---|
| 32,768 | 32,731–32,839 | 3 | 4.344 | 15.365 | `glm53-promoted-retrieval-32768-20261031T143209.751154Z.json` |
| 100,000 | 99,768–99,806 | 3 | 13.500 | 5.027 | `glm53-promoted-retrieval-100000-20261031T143224.225601Z.json` |
| 200,000 | 199,221–199,394 | 3 | 27.914 | 2.557 | `glm53-promoted-retrieval-200000-20261031T143307.160521Z.json` |
| 260,000 | 259,232–259,453 | 3 | 37.003 | 1.932 | `glm53-promoted-retrieval-260000-20261031T143435.065091Z.json` |
| 1,000,000 | 995,864–995,961 | 2 | **175.287** | 0.401 | `glm53-promoted-retrieval-1m-20261031T143718.147710Z.json` |

End-to-end output rate for retrieval is dominated by cold prefill; 0.401 tok/s
does not mean decode runs at that rate. The two 1M TTFT values were **175.200 /
175.373 s**. Their ~175.3 s median is essentially the earlier old-build matched
175.308 s, so the pre-promotion +6.37% single-pair slowdown was **not reproduced**.
These are different synthetic documents and few samples; no cause, significance
or general speedup is established. Earlier results remain intact.

### Long decode and mixed-load screen — complete

100K decode: actual prompt counts 99,750 / 99,909 / 99,792, 256 forced output
tokens each, three requests; median TTFT **13.603 s**, aggregate **17.014 tok/s**,
per-request decode estimate **176.798 tok/s**. Evidence:
`glm53-promoted-decode-100k-20261031T143631.251609Z.json`.

Mixed: one **199,396-token** cold retrieval while another request generated
**4,096 forced tokens**. Telemetry observed real decode/prefill overlap; all codes
were found, traffic delta was exactly two, retrieval TTFT **34.186 s**, total
screen **53.535 s**, longest observed content-event gap **0.188 s**. Evidence:
`glm53-promoted-mixed-200k-20261031T144321.213968Z.json`.

The two 1M streams each received **11 SSE keepalive comments** during prefill;
the mixed retrieval received two. Local SSE operation is verified, not a proxy's
or external gateway's idle-timeout behavior.

### Audit, memory and final state

All **14 capacity workloads + one mixed workload passed**, including 74 measured
capacity requests, seven warmups and two mixed requests. Each capacity report
verified the exact promoted image and expected request-counter delta; no unexpected
inference traffic, observed OOM, benchmark-time container restart or GPU-sampling
error occurred. The final health counter was 95 (12 promotion smoke/agent requests
plus 83 benchmark requests). Do not count warmups as measured samples.

Minimum sampled free HBM during the suite, also observed after it, was **6,889 MiB
on GPU 0** and **8,145 MiB on GPUs 1-3** (~6.73 / 7.95 GiB). After the suite the
service was healthy/idle, context **1,048,576**, pool **4,345,856**, free pool
**4,343,808** tokens; one kept prompt used 37,105,280 bytes outside the pool.
Allocator/kernel/cache retention affects idle memory. Sampled minima are not
guaranteed transient headroom; do not increase pool/concurrency from this result.

Final serving state: promoted image running with `unless-stopped`; old GLM and
Qwen stopped/preserved with `no`. No removals, optional tuning, restarts after
the benchmark suite, or installed-engine source modifications were needed.

Derived summary and final allowlisted state/audit:
`evidence/glm53-production-benchmark-summary-20261031T144546203860Z.json`.
All 147 offline repository tests pass. Full raw build/runtime logs remain outside
this public repository; only allowlisted audit summaries and synthetic test
responses are recorded here.

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
