# GLM-5.3-Flash EXL3 benchmark results

Profile: [`glm53-flash-exl3-1m`](../configs/glm53-production.json). Capacity-first
policy: work completion and runtime health are the gates; queueing, latency and
sampled free memory are reported. Every report is timestamped under `evidence/`;
failed reports are retained.

**Alias/port note:** the benchmark evidence below was captured while the same
service was exposed as `GLM-5.3-Flash-EXL3` on `:8888`. The production service now
serves the same checkpoint, engine and settings as **`pratt-medium` on `:8011`**.
The post-change smoke re-run is recorded below; the capacity numbers are unchanged
by the alias/port.

## Interface smoke

Post-alias/port report:
`evidence/glm53-pratt-medium-smoke-20261019-20261019T150711.895394Z.json`
(served as `pratt-medium` on `:8011`). Earlier smoke reports before the alias/port
change remain under `evidence/glm53-production-smoke-*`.

| Check | Result |
|---|---|
| Chat | `H100-READY`, 0.07 s |
| Reasoning | separated `reasoning_content`, final `42`, 0.36 s |
| Tool call | `lookup_room({"room_id": "B204"})`, 0.11 s |
| Vision | synthetic red PNG answered `Red.`, 1.86 s |

## Short decode, ~1,000 input / 256 forced output

| Workload | Rounds | Median aggregate | Median per-request decode estimate | TTFT p50 | Report |
|---|---:|---:|---:|---:|---|
| c1 cold | 3 | **197.3 tok/s** | 223.0 tok/s | 0.149 s | `evidence/glm53-short-c1-cold-final-20261019T145359.740723Z.json` |
| c2 cold | 3 | **253.2 tok/s** | 159.9 tok/s | 0.233 s | `evidence/glm53-short-c2-cold-final-20261019T145410.022112Z.json` |
| c4 cold | 3 | **360.4 tok/s** | 110.3 tok/s | 0.399 s | `evidence/glm53-short-c4-cold-final-20261019T145420.408841Z.json` |
| c1 warm | 3 | **243.1 tok/s** | 245.2 tok/s | 0.010 s | `evidence/glm53-short-c1-warm-final-20261019T145437.526343Z.json` |
| c4 warm | 3 | **496.9 tok/s** | 139.9 tok/s | 0.041 s | `evidence/glm53-short-c4-warm-final-20261019T144441.091134Z.json` |

Definitions:

- **Aggregate** = total actual completion tokens in a round / client wall time.
- **Per-request decode estimate** = completion tokens / (client elapsed - first
  visible text), median over samples. It excludes queueing/prefill but is not a
  kernel-level token interval; DFlash2 can put several tokens in one stream event.
- p95 is omitted below 30 samples; three-round screens are not production tails.
- Warm means the exact prompt was pre-filled once, then reused. The harness
  requires at least 90% reported prompt-cache hits on every measured request.

## Long-context retrieval, c1 cold, 256 output

Three codes are placed at the beginning, middle and end of each document; the
model must return all three.

| Prompt target | Actual prompt | Rounds | TTFT p50 | Median aggregate | Codes recovered | Report |
|---:|---:|---:|---:|---:|---|---|
| 32,768 | 32,845 | 3 | 4.330 s | 15.48 tok/s | 3/3 | `evidence/glm53-32k-retrieval-c1-cold-20261019T144456.011602Z.json` |
| 100,000 | 99,859 | 3 | 13.564 s | 5.22 tok/s | 3/3 | `evidence/glm53-100k-retrieval-c1-cold-20261019T144517.805831Z.json` |
| 200,000 | 199,313 | 3 | 27.929 s | 2.55 tok/s | 3/3 | `evidence/glm53-200k-retrieval-c1-cold-20261019T144612.499971Z.json` |
| 260,000 | 259,422 | 3 | 36.998 s | 1.85 tok/s | 3/3 | `evidence/glm53-260k-retrieval-c1-cold-20261019T144748.958359Z.json` |
| 1,000,000 | 995,743 | 1 | **175.244 s** | 0.382 tok/s | 3/3 | `evidence/glm53-1m-retrieval-c1-cold-20261019T144950.870150Z.json` |

The end-to-end rate is dominated by cold prefill. The prefill rate from the
one-request screens is roughly 7.0-7.5K tok/s at 32K-260K and ~5.7K tok/s at 1M
(prompt tokens / TTFT). The 1M row is a **single bounded screen**, not a
production-tail or universal long-context guarantee.

## Long-context decode

| Workload | Actual prompt | Rounds | TTFT p50 | Median aggregate | Decode estimate | Report |
|---|---:|---:|---:|---:|---:|---|
| 100K c1 cold, 256 output | 99,863 | 3 | 13.602 s | 17.15 tok/s | 194.7 tok/s | `evidence/glm53-100k-decode-c1-cold-20261019T145257.246248Z.json` |

## Findings

1. **Kept prompt states.** The engine's default `TF_GLM_CACHE_ENTRIES=8` was too
   small for four concurrent conversations plus prior benchmark states; the
   production service sets the recipe's `TF_GLM_CACHE_ENTRIES=32`. Separately, a
   warmup that generated 64 unforced tokens did not leave all four concurrent
   prompt states reusable, while a forced 1-token warmup did; the decode warmup
   now uses the forced 1-token form. Both failed warm attempts are retained under
   `evidence/glm53-short-c4-warm-*.json`.
2. **NCCL plugin.** The NGC image's `NCCL_NET_PLUGIN=spcx` is for Spectrum-X/RDMA
   and killed the ranks on this host. `NCCL_NET_PLUGIN=none` plus
   `NCCL_GIN_ENABLE=0` initializes cleanly over NVLink.
3. **Image architecture.** The upstream GHCR image is arm64-only; this host runs
   a locally built amd64 image from the same TensorFold v0.6.0 + patches.
4. **1M window.** The engine chose 1,048,576 tokens at 48.18 GiB (ranks 1-3) and
   49.98 GiB (rank 0 with vision) within the 67.80 GiB budget. The pool is
   2,754,560 tokens.
5. **Prompt sizes.** The chat-route tokenizer differs from `/tokenize` by a few
   template tokens and the builder targets within ~0.5%; the actual reported
   prompt tokens are in the tables and every evidence file.

## Caveats

- `DENSE=q4` and `KV=fp8` are the recipe's lossy defaults; compared with BF16,
  quality-sensitive workloads may regress.
- DFlash2 is CC BY-NC-ND 4.0, non-commercial use only.
- The production profile uses the model/quantization/drafter/parallel/context
  recipe, but leaves the optional GB10-specific speed envs at engine defaults.
  Further optimization is a separate experiment.
- The 1M screen is one bounded retrieval request, not a universal long-context
  guarantee. No sustained-load or overload test was run.
- Vision was validated with one synthetic red image, not image/video quality.
- p95 latency is omitted for every table (fewer than 30 samples); the three-round
  screens are screening evidence, not production tails.
