# H100 inference production workspace — GLM-5.3-Flash EXL3

Latest deployment: [GLM-5.3-Flash EXL3, TP4, 1M context, DFlash2](docs/GLM53_PRODUCTION.md).
Interface smoke and bounded short/long-context screens passed; production-tail,
sustained-load and overload qualification remain open.

**Promoted on 2026-10-31 with operator approval:** recipe patch hash
`789e8f3bdfa2` (123 patches), retaining the existing model, endpoint and memory
policy. [Promotion and fresh benchmarks](docs/GLM53_PROMOTION_20261031.md),
[build/CPU checks](docs/GLM53_CANDIDATE_BUILD.md), and
[pre-promotion validation](docs/GLM53_UPDATE_VALIDATION.md).
The operator accepted monitored promotion after a single matched pre-promotion
1M screen had 6.4% longer TTFT; that observation is not erased or a general
performance guarantee. Fresh post-promotion benchmarks all passed; two prompt-cold
1M requests measured **175.3 s median TTFT**, so that earlier slowdown was not
reproduced. Its cause remains unproven, and production monitoring continues.

Evidence-first TensorFold experiments for **4× NVIDIA H100 80GB HBM3** serving
`pratt-medium` (the GLM-5.3-Flash EXL3 checkpoint) at `http://127.0.0.1:8011/v1`.
Adapted from the
[GLM-5.3-Flash EXL3 2×DGX-Spark TensorFold recipe](https://github.com/MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold),
pinned recipe commit `bf5f945`. The harness here is GLM-specific; the previous Qwen
workspace documentation remains in `docs/` and the parent commit.

**Current service (2026-10-31, 14:29 UTC):** `tensorfold-glm53-candidate-789e8f3bdfa2` is
serving as `pratt-medium` on the existing production endpoint
`http://127.0.0.1:8011/v1`, verified ready/idle after interface smoke
(chat, separated reasoning, tool call and vision). It runs TensorFold v0.6.0 plus
the recipe's 123 patches at **TP4**, **4 concurrent streams**, the native
**1,048,576-token context**, and a **4,345,856-token shared pool**. DFlash2 drafts,
vision is enabled, and thinking is on by default. The restart policy is
`unless-stopped`. Promotion readiness took **150.77 s**. After interface/agent
checks, before benchmarking, sampled free HBM was **9,105 MiB on GPU 0** and
**10,361 MiB on GPUs 1-3**; long-load headroom can be lower. The versioned
container name retains `candidate` for identity continuity, but it is now the
production service. Old GLM and Qwen are stopped/preserved with `restart=no`.

## Production recipe

| Setting | Captured value |
|---|---|
| Model | `Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold` @ `078455f…` |
| Served id | `pratt-medium` (same id/port as the previous service) |
| Engine | TensorFold v0.6.0 + MiaAI-Lab recipe patches |
| Image | `tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100` (`sha256:09cb4a76…`, amd64) |
| Container | `tensorfold-glm53-candidate-789e8f3bdfa2` (promoted, same validated identity) |
| Recipe | `bf5f945`, patch/extras hash `789e8f3bdfa2`, 123 patches |
| Parallelism | TP4, one rank per H100; NCCL over NVLink |
| Context | 1,048,576 tokens |
| Shared pool | 4,345,856 tokens |
| Concurrent streams | 4 |
| Quantization | EXL3 4-bit routed experts; q4 dense; FP8 KV |
| Drafter | DFlash2 (CC BY-NC-ND 4.0, internal non-commercial use) |
| Vision / thinking | enabled / on by default |
| Default reply budget | 32,768 tokens |
| Memory reserve / pool cap | 5 GiB / 22.5 GiB per GPU |
| Pre-benchmark free HBM | 9,105 MiB GPU 0; 10,361 MiB GPUs 1-3 (not a long-load guarantee) |
| Post-benchmark / minimum sampled free HBM | 6,889 MiB GPU 0; 8,145 MiB GPUs 1-3 |
| Kept prompt states | 32 (`TF_GLM_CACHE_ENTRIES`) |
| Restart policy | `unless-stopped` |
| API / health | `http://127.0.0.1:8011/v1`, `/health` |

The exact profile, observed memory, rollback target and platform notes are in
[`configs/glm53-production.json`](configs/glm53-production.json).

## Preserved rollback

Primary rollback is the **old GLM container/image**, stopped and preserved. In an
approved idle/drained window, stop the promoted service before restoring it:

```bash
docker update --restart no tensorfold-glm53-candidate-789e8f3bdfa2
docker stop -t 60 tensorfold-glm53-candidate-789e8f3bdfa2
docker update --restart unless-stopped tensorfold-glm53-flash-exl3-1m
docker start tensorfold-glm53-flash-exl3-1m
# Verify JSON health/model/context; update the production record to match rollback.
```

The old image is `tensorfold-glm53:v0.6.0-h100` (`sha256:b8f133b9…`); its repaired
idempotent entrypoint and real restart were verified. Qwen remains a separate
secondary fallback (262,144 context, SGLang TP4/EP4), also stopped/preserved.
Do not remove either rollback image/container. Never start another full model
while the serving model owns the GPUs. See [the runbook](docs/GLM53_RUNBOOK.md).

## Benchmark results

Promotion smoke and all six agent/API checks passed. Fresh post-promotion short
screens below each ran three rounds with ~1,024 input / 256 forced output tokens.
Aggregate is output tokens / client wall time including prefill; decode is a
per-request estimate excluding TTFT, not kernel throughput. No p95 below 30 samples.

| Workload | Aggregate tok/s | Decode estimate tok/s/request | TTFT p50 |
|---|---:|---:|---:|
| c1 cold greedy | 180.2 | 202.1 | 0.152 s |
| c2 cold greedy | 241.2 | 138.8 | 0.232 s |
| c4 cold greedy | 372.2 | 118.9 | 0.407 s |
| c1 warm greedy | 220.7 | 222.4 | 0.008 s |
| c2 warm greedy | 301.3 | 162.7 | 0.020 s |
| c4 warm greedy | 465.4 | 125.5 | 0.054 s |
| c1 cold sampled | 172.8 | 192.9 | 0.153 s |
| c4 cold sampled | 357.3 | 109.9 | 0.404 s |

Sampled: temperature 1 / top-p 0.95; greedy: temperature 0. Warm runs verified at
least 90% reported prompt reuse. All eight screens passed with isolated traffic
and no observed OOM.

### Post-promotion long-context retrieval

Cold prompt cache, 256-token reply budget; all three requested access codes were
recovered in every request. Compiled kernel caches were already available.

| Target | Actual prompt range | Requests | TTFT median |
|---|---:|---:|---:|
| 32K | 32,731–32,839 | 3 | 4.344 s |
| 100K | 99,768–99,806 | 3 | 13.500 s |
| 200K | 199,221–199,394 | 3 | 27.914 s |
| 260K | 259,232–259,453 | 3 | 37.003 s |
| ~1M | 995,864–995,961 | 2 | **175.287 s** |

100K cold decode (256 forced output, three requests): **13.603 s TTFT**, **176.8
tok/s/request decode estimate**, **17.01 tok/s end-to-end aggregate**.

Mixed load passed: a **199,396-token** cold retrieval alongside **4,096 forced
decode tokens**, observed real decode/prefill overlap, **34.186 s** retrieval TTFT,
and **0.188 s** longest observed content-event gap. Both 1M streams received 11
SSE keepalive comments while prefilling. No external gateway qualification is implied.

All **15 bounded benchmark workloads** passed: 74 measured capacity requests,
seven warmups and two mixed requests, with isolated traffic, no observed OOM,
no container restart, and no GPU-sampling errors. Final service was healthy/idle;
minimum sampled free HBM was **6,889 / 8,145 MiB** (GPU 0 / others). These are
sampled values, not guaranteed transient headroom. No p95/p99 or sustained-load
qualification is claimed. Full evidence and methodology are in
[`docs/GLM53_PROMOTION_20261031.md`](docs/GLM53_PROMOTION_20261031.md).
Earlier measurements remain in [`docs/GLM53_RESULTS.md`](docs/GLM53_RESULTS.md)
and the pre-promotion validation report; they are not relabeled as new-image runs.

## Platform changes from the 2×Spark recipe

1. **amd64 image.** The published GHCR image is `linux/arm64` only. This host runs
   a locally built `linux/amd64` image from the same TensorFold v0.6.0 + all
   `patches/*.patch`.
2. **One container, four ranks.** Each rank is pinned to one GPU with
   `TF_GLM_DEVICE`; all four GPUs stay visible so NCCL uses NVLink. TensorFold's
   device selector is baked into the new image; startup never rewrites engine
   source. A real restart verified that source hashes remained identical.
3. **No Spectrum-X plugin.** The NGC image sets `NCCL_NET_PLUGIN=spcx`, which
   fails on this non-RDMA host. The service uses `NCCL_NET_PLUGIN=none` and
   `NCCL_GIN_ENABLE=0`.
4. **Kept prompt states.** The engine default of 8 was too small for four
   concurrent conversations plus prior states; the recipe's
   `TF_GLM_CACHE_ENTRIES=32` is set. A forced 1-token warmup is used for decode
   cache warming because a longer unforced warmup did not preserve all four
   concurrent prompt states.
5. **Memory profile.** This host is dedicated to inference, so the KV pool was
   raised from 12.5 to **22.5 GiB** and the planning reserve lowered from 10 to
    **5 GiB**. The new image retains this **4,345,856-token pool**. Historical
    calibration remains in the profile under explicitly historical keys. New-image
    pre-promotion long/mixed screens sampled **6,813 / 8,067 MiB free** on GPU 0 /
    other GPUs; current promotion measurements are separately recorded. Allocator
    retention and cached states affect headroom. Four simultaneous 1M-token requests
    are not stress-tested; do not increase the pool/concurrency based on idle HBM.

## Measurement policy

Capacity-first: work completion, runtime health, token accounting and telemetry
are separate. Queueing, latency and sampled free memory are reported, not
automatic failures. Every report is timestamped under `evidence/`, including
failed and partial runs. Cold prompts carry unique markers; warm runs require at
least 90% reported prompt-cache reuse. Prompt sizes are targets; both `/tokenize`
and the server's reported prompt-token count are recorded for every sample.

`production_qualified` remains false for these bounded screens. No sustained
load, overload, fairness, coding-quality, or external-gateway test is implied.

## Offline checks

```bash
cd /home/tngai/H100-Node-Config
python3 -B -m unittest discover -s tests -v        # 147 offline tests
python3 -B tests/glm_smoke.py --label glm53-smoke --execute --confirm-idle --vision
python3 -B tests/glm_benchmark.py --label glm53-short-c1-cold \
  --profile glm53-flash-exl3-1m --mode decode --cache cold --concurrency 1 \
  --prompt-tokens 1024 --output-tokens 256 --rounds 3 \
  --execute --confirm-idle
```

The smoke and benchmark commands **send inference** and require an idle service
plus both confirmation flags. Each invocation is one bounded workload; there is
no unattended full-matrix runner. Reports are created exclusively under
`evidence/` and never overwritten.

## Contents

- `configs/glm53-production.json`: current production profile and rollback record.
- `configs/glm53-workloads.json`: staged benchmark matrix and qualification scope.
- `tests/glm_common.py`: TensorFold client, prompt builder, SSE parsing, audit.
- `tests/glm_smoke.py`: chat, reasoning, tool-call and vision smoke.
- `tests/glm_benchmark.py`: capacity-first short/long decode and retrieval harness.
- `tests/test_glm_harness.py`: offline unit tests for the GLM harness.
- `evidence/glm53-*.json`: timestamped smoke and benchmark reports, including failures.
- `docs/GLM53_PRODUCTION.md`: cutover, platform changes and rollback.
- `docs/GLM53_RESULTS.md`: full benchmark tables, definitions and caveats.
- `docs/GLM53_RUNBOOK.md`: read-only checks, restart and benchmark commands.
- `docs/`: the previous Qwen workspace history remains available.

## Qualification boundary

- `DENSE=q4` and `KV=fp8` are the recipe's lossy defaults; quality-sensitive
  workloads may regress compared with BF16.
- DFlash2 is CC BY-NC-ND 4.0, non-commercial use only.
- The production profile uses the model/quantization/drafter/parallel/context
  recipe, but leaves the optional GB10-specific speed envs at engine defaults.
- Post-promotion 1M results are two bounded requests, not a universal long-context
  guarantee. Vision smoke uses a synthetic red image. No sustained load, overload,
  fairness, broad quality, external-gateway, or production-tail qualification was run.
