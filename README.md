# H100 inference production workspace — GLM-5.3-Flash EXL3

Latest deployment: [GLM-5.3-Flash EXL3, TP4, 1M context, DFlash2](docs/GLM53_PRODUCTION.md).
Interface smoke and bounded short/long-context screens passed; production-tail,
sustained-load and overload qualification remain open.

Evidence-first TensorFold experiments for **4× NVIDIA H100 80GB HBM3** serving
`pratt-medium` (the GLM-5.3-Flash EXL3 checkpoint) at `http://127.0.0.1:8011/v1`.
Adapted from the
[GLM-5.3-Flash EXL3 2×DGX-Spark TensorFold recipe](https://github.com/MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold),
reference recipe v1.10. The harness here is GLM-specific; the previous Qwen
workspace documentation remains in `docs/` and the parent commit.

**Current service (2026-10-19, 14:36 UTC):** `tensorfold-glm53-flash-exl3-1m` is
serving as `pratt-medium` on the existing production endpoint
`http://127.0.0.1:8011/v1`, verified ready/idle after interface smoke
(chat, separated reasoning, tool call and vision). It runs TensorFold v0.6.0 plus
the recipe's patches at **TP4**, **4 concurrent streams**, the native
**1,048,576-token context**, and a **2,754,560-token shared pool**. DFlash2 drafts,
vision is enabled, and thinking is on by default. The restart policy is
`unless-stopped`. GPU memory is ~64.4 GB on rank 0 and ~63.1 GB on ranks 1-3;
the startup estimate is 49.98 / 48.18 GiB within 67.80 GiB, and a warm load took
150.5 s. The preserved Qwen service is stopped and can be restored with
`docker start sglang-qwen38-flash-next-088-mamba070-20261016t020846`.

## Production recipe

| Setting | Captured value |
|---|---|
| Model | `Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold` @ `078455f…` |
| Served id | `pratt-medium` (same id/port as the previous service) |
| Engine | TensorFold v0.6.0 + MiaAI-Lab recipe patches |
| Image | `tensorfold-glm53:v0.6.0-h100` (`sha256:b8f133b9…`, amd64) |
| Container | `tensorfold-glm53-flash-exl3-1m` |
| Parallelism | TP4, one rank per H100; NCCL over NVLink |
| Context | 1,048,576 tokens |
| Shared pool | 2,754,560 tokens |
| Concurrent streams | 4 |
| Quantization | EXL3 4-bit routed experts; q4 dense; FP8 KV |
| Drafter | DFlash2 (CC BY-NC-ND 4.0, internal non-commercial use) |
| Vision / thinking | enabled / on by default |
| Default reply budget | 32,768 tokens |
| Memory reserve / pool cap | 10 GiB / 12.5 GiB per GPU |
| Kept prompt states | 32 (`TF_GLM_CACHE_ENTRIES`) |
| Restart policy | `unless-stopped` |
| API / health | `http://127.0.0.1:8011/v1`, `/health` |

The exact profile, observed memory, rollback target and platform notes are in
[`configs/glm53-production.json`](configs/glm53-production.json).

## Preserved rollback

The Qwen service container is **stopped and preserved**, not removed:

```bash
docker stop tensorfold-glm53-flash-exl3-1m
docker start sglang-qwen38-flash-next-088-mamba070-20261016t020846
# wait for http://127.0.0.1:8011/v1/models
```

Qwen baseline: `pratt-medium`, 262,144 context, SGLang TP4/EP4, image
`sha256:4175343ed77b…`. Do not remove the Qwen container or image. The Qwen
workspace's own `docs/PRODUCTION_RECIPE.md` remains the authority for its
qualification history.

## Benchmark results

Full tables, definitions and evidence links:
[`docs/GLM53_RESULTS.md`](docs/GLM53_RESULTS.md).

### Interface smoke

| Check | Result |
|---|---|
| Chat | `H100-READY`, 0.07 s |
| Reasoning | separated `reasoning_content`, final `42`, 0.36 s |
| Tool call | `lookup_room({"room_id": "B204"})`, 0.11 s |
| Vision | synthetic red PNG answered `Red.`, 1.86 s |

### Short decode, ~1,000 input / 256 forced output

| Workload | Rounds | Median aggregate | Median per-request decode | TTFT p50 |
|---|---:|---:|---:|---:|
| c1 cold | 3 | **197.3 tok/s** | 223.0 tok/s | 0.149 s |
| c2 cold | 3 | **253.2 tok/s** | 159.9 tok/s | 0.233 s |
| c4 cold | 3 | **360.4 tok/s** | 110.3 tok/s | 0.399 s |
| c1 warm | 3 | **243.1 tok/s** | 245.2 tok/s | 0.010 s |
| c4 warm | 3 | **496.9 tok/s** | 139.9 tok/s | 0.041 s |

### Long-context retrieval, c1 cold, 256 output

| Prompt target | Actual prompt | Rounds | TTFT p50 | Median aggregate | Codes |
|---:|---:|---:|---:|---:|---|
| 32,768 | 32,845 | 3 | 4.330 s | 15.48 tok/s | 3/3 |
| 100,000 | 99,859 | 3 | 13.564 s | 5.22 tok/s | 3/3 |
| 200,000 | 199,313 | 3 | 27.929 s | 2.55 tok/s | 3/3 |
| 260,000 | 259,422 | 3 | 36.998 s | 1.85 tok/s | 3/3 |
| 1,000,000 | 995,743 | 1 | **175.244 s** | 0.382 tok/s | 3/3 |

A 100K c1 cold decode screen (256 forced output) also passed: TTFT 13.602 s,
median aggregate 17.15 tok/s, per-request decode estimate 194.7 tok/s.

The 1M row is a single bounded retrieval request, not a production-tail or
universal long-context guarantee. p95 is omitted for every workload (fewer than
30 samples); three-round screens are screening evidence.

## Platform changes from the 2×Spark recipe

1. **amd64 image.** The published GHCR image is `linux/arm64` only. This host runs
   a locally built `linux/amd64` image from the same TensorFold v0.6.0 + all
   `patches/*.patch`.
2. **One container, four ranks.** Each rank is pinned to one GPU with
   `TF_GLM_DEVICE`; all four GPUs stay visible so NCCL uses NVLink. TensorFold's
   hardcoded `torch.cuda.set_device(0)` is patched at container start.
3. **No Spectrum-X plugin.** The NGC image sets `NCCL_NET_PLUGIN=spcx`, which
   fails on this non-RDMA host. The service uses `NCCL_NET_PLUGIN=none` and
   `NCCL_GIN_ENABLE=0`.
4. **Kept prompt states.** The engine default of 8 was too small for four
   concurrent conversations plus prior states; the recipe's
   `TF_GLM_CACHE_ENTRIES=32` is set. A forced 1-token warmup is used for decode
   cache warming because a longer unforced warmup did not preserve all four
   concurrent prompt states.
5. **Memory.** The 1M window and 2,754,560-token pool fit in 80 GB H100s because
   the engine budgets from HBM on a discrete GPU (67.80 GiB budget per rank).

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
python3 -B -m unittest discover -s tests -v        # 119 tests
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

- `configs/glm53-production.json`: frozen production profile and rollback record.
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
- The 1M screen is one request. Vision was one synthetic red image. No sustained
  load, overload, fairness, or production-tail qualification was run.
