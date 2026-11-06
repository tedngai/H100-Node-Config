# GLM-5.3-Flash EXL3 production cutover

## Current production — 2026-11-06 serving-limit change

The operator approved reducing context to **400,000 tokens per request, prompt
plus reply**, then raising maximum concurrency to **8**. This is not a cumulative
per-user quota. The same immutable image, weights, TP4, DFlash2, vision/thinking,
32,768-token default reply budget, 22.5 GiB pool cap and 5 GiB reserve are retained.
No engine upgrade was installed.

| Item | Current value |
|---|---|
| Container | `tensorfold-glm53-400k-p8-20261106t165335` |
| Image | `tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100`, `sha256:09cb4a76…` (unchanged) |
| Endpoint / model | `http://127.0.0.1:8011/v1` / `pratt-medium` (unchanged) |
| Context / shared pool / maximum streams | 400,000 / 3,698,688 tokens / 8 |
| Fresh-start free HBM | 12,444 MiB GPU 0; 13,598 MiB GPUs 1-3 |
| Validation | Subsequent bounded interfaces, actual eight-way decoding, near-400k retrieval, limit refusals and 11-minute memory soak passed; not multi-day qualification |
| Restart policy | Selected container `unless-stopped`; all preserved alternatives `no` |
| Primary rollback | `tensorfold-glm53-candidate-789e8f3bdfa2`, previous 1M/4-stream configuration, same image |
| Intermediate fallback | `tensorfold-glm53-400k-p4-20261106t165335`, startup-checked at 400k/4 |

Changes were separated: 400k/4 startup passed in 176.265 s, then 400k/8 in
156.111 s. All previous containers were retained. Rank logs use fresh external
directories; the kernel cache was reused. The pool shrank automatically with the
window; stream capacity is not a measurement of actual concurrency or throughput.
Fresh-start headroom does not establish sustained-load stability.

Subsequent [400k/8-stream validation](GLM53_400K_VALIDATION_20261106.md) passed
212 requests across separately isolated passing phases, including eight warmups,
plus two expected context refusals. The 120-request / 662.8 s soak was effectively
flat in GPU memory (+2 MiB GPU0, unchanged GPUs1–3 between first/last post-batch
idle samples); final-run minimum free HBM was 10,202/11,470 MiB. These short
measurements do not establish a fix for long-run memory growth.

See [change evidence](../evidence/glm53-context-concurrency-change-20261106T165335760866Z.json),
the [authoritative profile](../configs/glm53-production.json), and the
[current runbook](GLM53_RUNBOOK.md). The October 31 benchmarks below remain
historical results at 1M/4, not qualification of the new configuration.

## Historical image promotion — 2026-10-31, 1M context / 4 streams

The operator explicitly approved promoting the validated `789e8f3bdfa2` build
after review of the pre-promotion single-pair 1M timing caveat. It is serving as
`pratt-medium` on the unchanged `http://127.0.0.1:8011/v1` endpoint.

| Item | Current value |
|---|---|
| Container | `tensorfold-glm53-candidate-789e8f3bdfa2` (validated name/identity retained, production role) |
| Image | `tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100`, `sha256:09cb4a76…` |
| Recipe | commit `bf5f945`, 123 patches, hash `789e8f3bdfa2` |
| Restart policy | `unless-stopped`; old GLM and Qwen stopped with `no` |
| Context / pool / streams | 1,048,576 / 4,345,856 tokens / 4 |
| TP / transport | 4 H100 ranks / NCCL over NVLink |
| Precision / drafter | EXL3 routed experts, q4 dense, fp8 KV / same pinned DFlash2 |
| Pool cap / reserve | 22.5 GiB / 5 GiB, unchanged |
| Promotion readiness | 150.77 s |
| Primary rollback | `tensorfold-glm53-flash-exl3-1m`, image `sha256:b8f133b9…`, stopped/preserved |

The new device selector and supervisor are baked into the image; startup does
not mutate engine source. A real restart preserved the container/image/source
hash and passed post-restart smoke. Full promotion smoke and agent/API checks
passed before setting the serving restart policy.

The authoritative current profile is
[`configs/glm53-production.json`](../configs/glm53-production.json); post-promotion
measurements are in [the promotion report](GLM53_PROMOTION_20261031.md).
Use [the current runbook](GLM53_RUNBOOK.md), not the older external remove/recreate
scripts. No optional performance tuning, new weights, container removal or image
rebuild accompanied promotion.

## Historical initial cutover — 2026-10-19

The remaining sections preserve the original deployment/calibration history.
They are **not current service/rollback instructions** after the 2026-10-31
promotion. Original cutover had operator approval to run GLM and stop Qwen.

### Historical service

| Item | Value |
|---|---|
| Endpoint | `http://127.0.0.1:8011/v1` |
| Model id | `pratt-medium` (served alias for GLM-5.3-Flash EXL3) |
| Container | `tensorfold-glm53-flash-exl3-1m` |
| Image | `tensorfold-glm53:v0.6.0-h100` (`sha256:b8f133b9…`) |
| Restart policy | `unless-stopped` |
| GPUs | 4x NVIDIA H100 80GB HBM3, one rank per GPU, NVLink/NCCL |
| Engine | TensorFold v0.6.0 + MiaAI-Lab recipe patches |
| Checkpoint | `Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold` @ `078455f…` |
| Context | **1,048,576 tokens** |
| Shared pool | **4,345,856 tokens** |
| Concurrent streams | 4 |
| Quantization | EXL3 4-bit routed experts, q4 dense, FP8 KV |
| Drafter | DFlash2 (CC BY-NC-ND 4.0, internal non-commercial use) |
| Vision / thinking | enabled / thinking on by default |
| Default reply budget | 32,768 tokens |
| Memory reserve / pool cap | 5 GiB / 22.5 GiB per GPU |
| GPU memory in service | ~72.2 GB rank 0, ~71.0 GB ranks 1-3 |
| Idle free HBM | ~8.7 GiB rank 0, ~9.8 GiB ranks 1-3 |
| Startup estimate | 49.98 GiB rank 0 (vision), 48.18 GiB ranks 1-3, within 72.80 GiB |
| Warm load time | 173.8 s |

`GET /health` reports `ok: true`, `context_length: 1048576`,
`streams.max: 4`, and a `pool_tokens` figure of 4,345,856. The served id is
`pratt-medium` on port `8011`, matching the previous service, so existing
clients keep the same model id and endpoint while the engine behind it changes.

### Historical platform changes from the upstream 2x DGX Spark recipe

The upstream repository targets two GB10 Sparks over SSH and RoCE. This host is
one 4xH100 node, so the following are intentional differences:

1. **amd64 image.** The published GHCR image is `linux/arm64` only. The image here
   is built from the same `nvcr.io/nvidia/pytorch:26.07-py3` base, TensorFold
   v0.6.0 and all `patches/*.patch`, for `linux/amd64`.
2. **One container, four ranks.** Each rank is pinned to one GPU with
   `TF_GLM_DEVICE`; all four GPUs stay visible so NCCL uses NVLink. The engine's
   hardcoded `torch.cuda.set_device(0)` is patched at container start.
3. **No Spectrum-X plugin.** The NGC image sets `NCCL_NET_PLUGIN=spcx`, which
   fails on this non-RDMA host. The service uses `NCCL_NET_PLUGIN=none` and
   `NCCL_GIN_ENABLE=0`.
4. **Kept-prompt cap.** TensorFold's default is 8 kept prompt states; the recipe
   sets `TF_GLM_CACHE_ENTRIES=32`. The default caused a c4 warm benchmark to
   evict warm prompts, so the production service sets 32.
5. **End-of-turn and shared prefix.** `TF_GLM_ASSISTANT_ENDS=1` and
   `TF_GLM_SHARED_PREFIX=1` are set to the recipe defaults.

### Historical memory profile

This host is dedicated to inference, so the operator approved using the previously
free HBM for KV capacity and leaving about **8-10 GiB free** instead of 17-18 GiB.

| KV_POOL_GIB | Reserve | Pool tokens | Free rank 0 |
|---:|---:|---:|---:|
| 12.5 | 10 GiB | 2,754,560 | 17,326 MiB |
| 20.5 | 10 GiB | 3,600,384 | 13,512 MiB |
| 20.5 | 7 GiB | 4,028,416 | 10,918 MiB |
| 20.5 | 5 GiB | 4,028,416 | 10,918 MiB |
| **22.5** | **5 GiB** | **4,345,856** | **8,914 MiB** |

Final idle: **8.70 GiB free on rank 0**, **9.83 GiB on ranks 1-3**. A 1M-token
request can leave about **7.5 / 8.8 GiB** free until the service is restarted,
because the CUDA allocator retains transient buffers. Validation at this profile:
1M-token retrieval passed at **175.395 s TTFT** with all three codes, and 4-stream
cold decode passed at **350.6 tok/s** aggregate. Four simultaneous 1M-token
requests are **not** stress-tested; the pool is 4.35M tokens.

### Historical smoke evidence

Post-alias/port: `evidence/glm53-pratt-medium-smoke-20261019-20261019T150711.895394Z.json`.
Post-pool-change: `evidence/glm53-pool225-smoke-20261019T154105.229658Z.json`.
Pre-change runs remain under `evidence/glm53-production-smoke-*`.

| Check | Result |
|---|---|
| Chat | `H100-READY` |
| Reasoning | separated `reasoning_content`, final answer `42` |
| Tool call | `lookup_room({"room_id": "B204"})` |
| Vision | synthetic red PNG answered `Red.` |

### Historical Qwen rollback

The Qwen service container is **stopped and preserved**, not removed:

```bash
docker stop tensorfold-glm53-flash-exl3-1m
docker start sglang-qwen38-flash-next-088-mamba070-20261016t020846
# wait for http://127.0.0.1:8011/v1/models
```

Qwen baseline: `pratt-medium`, 262,144 context, SGLang TP4/EP4, image
`sha256:4175343ed77b…`. Its rollback record is in
[`../configs/glm53-production.json`](../configs/glm53-production.json) and the
Qwen workspace's `docs/PRODUCTION_RECIPE.md`.

### Historical qualification boundary

The production profile passed interface smoke, a 1M-token retrieval request and a
4-stream cold decode screen; full tables are in
[`GLM53_RESULTS.md`](GLM53_RESULTS.md). It is **not** a 4x1M concurrent,
sustained-load, overload, fairness, or production-tail qualification. The
1M-context screen is a single bounded retrieval request, not a universal
long-context guarantee.
