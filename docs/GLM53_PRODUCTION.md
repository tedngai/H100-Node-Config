# GLM-5.3-Flash EXL3 production cutover

Cutover: **2026-10-19**, with operator approval to run GLM in production and to
stop the preserved Qwen service for the change window.

## Service

| Item | Value |
|---|---|
| Endpoint | `http://127.0.0.1:8888/v1` |
| Model id | `GLM-5.3-Flash-EXL3` |
| Container | `tensorfold-glm53-flash-exl3-1m` |
| Image | `tensorfold-glm53:v0.6.0-h100` (`sha256:b8f133b9…`) |
| Restart policy | `unless-stopped` |
| GPUs | 4x NVIDIA H100 80GB HBM3, one rank per GPU, NVLink/NCCL |
| Engine | TensorFold v0.6.0 + MiaAI-Lab recipe patches |
| Checkpoint | `Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold` @ `078455f…` |
| Context | **1,048,576 tokens** |
| Shared pool | **2,754,560 tokens** |
| Concurrent streams | 4 |
| Quantization | EXL3 4-bit routed experts, q4 dense, FP8 KV |
| Drafter | DFlash2 (CC BY-NC-ND 4.0, internal non-commercial use) |
| Vision / thinking | enabled / thinking on by default |
| Default reply budget | 32,768 tokens |
| Memory reserve / pool cap | 10 GiB / 12.5 GiB per GPU |
| GPU memory in service | ~64.4 GB rank 0, ~63.1 GB ranks 1-3 |
| Startup estimate | 49.98 GiB rank 0 (vision), 48.18 GiB ranks 1-3, within 67.80 GiB |
| Warm load time | 150.5 s |

`GET /health` reports `ok: true`, `context_length: 1048576`,
`streams.max: 4`, and a `pool_tokens` figure of 2,754,560.

## Platform changes from the upstream 2x DGX Spark recipe

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

## Smoke evidence

`evidence/glm53-production-smoke-20261019-20261019T143612.992314Z.json`

| Check | Result |
|---|---|
| Chat | `H100-READY` |
| Reasoning | separated `reasoning_content`, final answer `42` |
| Tool call | `lookup_room({"room_id": "B204"})` |
| Vision | synthetic red PNG answered `Red.` |

## Rollback

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

## Qualification boundary

The production profile passed interface smoke and the bounded benchmark screens in
[`GLM53_RESULTS.md`](GLM53_RESULTS.md). It is **not** a sustained-load, overload,
fairness, or production-tail qualification. The 1M-context screen is a single
bounded retrieval request, not a universal long-context guarantee.
