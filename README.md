# H100 inference optimization workspace

Latest deployment: [MTP-on with Mamba/KV ratio 0.7](docs/MAMBA_KV_ALLOCATION.md).
Startup and interface smoke passed; long-context performance is not yet requalified.

Evidence-first SGLang experiments for **4× NVIDIA H100 80GB HBM3** serving
`Qwen/Qwen3.8-Flash-Next-FP8` as `pratt-medium` at `http://127.0.0.1:8011`.
Adapted from [H200-Node-Config](https://github.com/tedngai/H200-Node-Config),
reference commit `0c2b32a7c5d62ea058207ead1c856d9544ac3f5a`. The harness here is
new, model-specific code; GLM-specific scripts and DP4 settings were not copied.

**Current service (2026-10-16, 02:22 UTC):** `memory-088-mamba-070` is serving at the
existing endpoint, verified ready/idle after three interface smoke checks. MTP is
enabled; static memory fraction remains 0.88. Shared token capacity is **1,806,656**
(**+5.21%** versus the preserved ratio-0.9 candidate), Mamba state slots are **570**,
and the effective request cap remains **48**. Per-request context remains 262,144.
The previous `sglang-qwen38-flash-next-088` container is stopped/preserved for rollback.
An initial ratio-0.7 screen passed 32K/512 cold decode at c1 (3/3; median aggregate
175.10 tok/s) and c6 (18/18; 367.98 tok/s). No OOM/retractions; queueing appeared at
c6. This is not a matched ratio-0.9 comparison or long-context qualification. Prior
ratio-0.9 benchmark results below do not qualify ratio 0.7. The latest ratio-0.9
capacity screen (20:00 UTC) passed 60/60 c6 cold
250K/4096 requests; median aggregate was 283.45 tok/s, initial p95 latency 86.21 s,
and minimum sampled free memory 1,629 MiB. The approved matched coding A/B also
completed 18/18 requests on each arm: MTP-on median aggregate 529.76 tok/s versus
403.39 tok/s with MTP disabled. The off arm had higher median TTFT/latency and no
observed OOM or retractions; queueing and low sampled free memory were advisory
warnings. SGLang's startup warmup explained the earlier loopback chat/API log entries;
the off candidate remains stopped/preserved. Original
baseline remains stopped/preserved. Larger contexts and universal
OOM safety remain unqualified. See
[`docs/MEMORY_FRACTION_FIRST.md`](docs/MEMORY_FRACTION_FIRST.md).

**Historical baseline status:** preliminary benchmarks and interface/retrieval checks recorded.
The original container was started with
approval after the operator's reboot. Post-reboot smoke and short c1/c2/c4/c6 cold
and two-pass warm screening passed, following an initial one-pass warm failure.
32K c1 cold/warm retrieval and cold/warm decode also passed. Strict no-queue 32K
c2 cold screening failed on waiting count 1. A separate
diagnostic supports transient prefill waiting; the strict failure remains failed.
Subsequently approved scheduling-aware screening passed c2/c4/c6 cold and warm.
The initial c6 warm attempt remains excluded after traffic overlap; a separate
three-round retry passed at median 1,023 tok/s with zero sampled waiting/retractions.
This is screening, not strict no-queue or production qualification. The 32K baseline
stage is complete. A 100K c1 cold retrieval screen subsequently passed three rounds
with all codes recovered, zero cache hits, and zero sampled waiting/retractions. The
first attempt was blocked at preflight; the later retry passed after fresh checks.
Further inference needs separate approval. Server settings remain unchanged.
The separately approved 200K and 260K c1 cold retrieval screens then passed three
rounds each; all codes were recovered with zero cache hits, sampled waiting, or
retractions. The 260K screen is still synthetic retrieval screening, not production
or full-context qualification. A repeat, full 262K prompt, or higher-load test needs
separate approval.
The separately approved 100K and 200K c1 cold/warm decode screens also passed:
warm timed requests reused 99,968/100,000 and 199,936/200,000 tokens after two
explicit warmups. These three-round screens do not establish tail or production
behavior. 260K decode and higher concurrency have not been tested.
Cached model revision metadata changed across
reboot, so pre/post-reboot results are not a matched comparison.
See [`docs/results.md`](docs/results.md). No candidate is performance-qualified.
For reboot recovery and immediate next actions, see
[`docs/INFERENCE_CONTEXT.md`](docs/INFERENCE_CONTEXT.md) and
[`docs/NEXT_EXPERIMENT.md`](docs/NEXT_EXPERIMENT.md).

## Preserved baseline

The immutable snapshot is [`configs/baseline.json`](configs/baseline.json), with
timestamped hardware/configuration evidence linked inside it.

| Setting | Captured value |
|---|---|
| Parallelism | TP4 / EP4 / DP1; one shared token pool |
| Context / maximum input | 262,144 total / 262,138 input tokens |
| Active-request cap | 48, automatically selected; not explicitly in launch argv |
| Shared token capacity | 1,587,968 |
| Static GPU memory fraction | 0.85 |
| Prefill chunk | 8,192 |
| KV dtype | `auto`; do not confuse FP8 model weights with explicit FP8 KV |
| Mamba state dtype | `bfloat16` |
| Linear attention | FlashInfer prefill/decode; Triton verification |
| Speculation | `NEXTN` launch flag; effective `EAGLE`, 3 steps / top-k 1 / 4 draft tokens |
| Parsers | Effective `qwen3` reasoning / `qwen3_coder` tools |
| Metrics / auto truncation | Both disabled |

The exact image ID, registry digest, overlay build labels, mount paths, network
settings, and launch argv are saved without the container environment or credentials.
The current container has no restart policy. Baseline recreation is **not** a
turnkey rollback: preserve the existing container and follow the runbook.

**Six 256K contexts are a theoretical token-slot fit, not a validated admission
guarantee.** Six near-full contexts leave little headroom and exceed this harness's
90% pool guard. Hybrid attention state and other runtime allocation also matter.

## Driver health after reboot

The pre-reboot host NVML/kernel mismatch was resolved by the operator's reboot:
host `nvidia-smi` now works at **580.178.04**. The original inference container is
running again. Future service changes still require a separately approved
maintenance window; do not start a second full model alongside this service.

## Offline checks — safe during production traffic

Host scripts need only Python 3's standard library. Future live prompt building
uses the existing container's locally cached Transformers tokenizer, on CPU.
No packages are installed during setup.

```bash
python3 -B -m unittest discover -s tests -v
python3 -B tests/profiles.py --list
python3 -B tests/profiles.py admission-6
python3 -B tests/profiles.py baseline --shell
python3 -B tests/summarize.py
python3 -B tests/validate_setup.py
```

`profiles.py` only prints resolved configuration or SGLang arguments. It cannot
deploy or restart anything. Candidates are relative to the original baseline,
not stacked on top of one another. See [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).

`validate_setup.py` saves an offline validation report. Its optional
`--inventory --check-tokenizer` flags additionally verify the live configuration
with read-only GET requests and build two short prompts on CPU using the cached
tokenizer. They do not load model weights or send inference.

A fresh **read-only** service/hardware inventory can be recorded with:

```bash
python3 -B tests/capture_baseline.py --label pretest-inventory
```

Do not repeat `--initialize`: baseline initialization is exclusive and refuses
to overwrite the existing snapshot. If authentication is added, the scripts can
read `SGLANG_API_KEY` from their process environment; they never save it.

## Live tests — separate approval and idle window required

**Current policy:** [capacity-first benchmarking](docs/BENCHMARK_POLICY.md).
Successful completion without observed OOM is the primary capacity criterion.
Queueing, latency, retractions and low sampled GPU-free memory are reported, not
automatic failures. `--policy no-queue` is optional; historical results are unchanged.

Follow [`docs/RUNBOOK.md`](docs/RUNBOOK.md) first. The examples below **send
inference** and must not be executed as part of setup:

```bash
python3 -B tests/smoke_test.py --label baseline-smoke --execute --confirm-idle
python3 -B tests/benchmark.py --label baseline-short-c1 --profile baseline \
  --concurrency 1 --prompt-tokens 1024 --output-tokens 256 --rounds 3 \
  --cache cold --execute --confirm-idle
```

Both confirmation flags are mandatory. Each invocation runs one bounded workload;
there is deliberately no unattended full-matrix runner. The workspace lock only
coordinates these scripts, not real users or other benchmark tools.

- Reports are exclusively created under `evidence/`, including failures and
  partial results. Existing files are never overwritten.
- Exact chat-formatted token IDs, early unique session markers, seeded natural
  filler, and three retrieval codes prevent misleading repeated-token probes.
- Cold runs isolate long prefixes but can still share short chat-template tokens.
  Warm runs verify at least 90% reported prefix reuse per measured request.
- Streaming timings use the client clock and actual final completion-token counts.
  TPOT is explicitly an estimate because speculative chunks can contain many tokens.
- The read-only `/v1/loads` endpoint provides sampled active/waiting counts in this
  build even with Prometheus disabled. No server change is needed to use it.
  Missing counters remain unknown, never assumed zero. Short requests can finish
  between load-snapshot publications.
- Forced-output throughput is not retrieval quality, coding quality, or gateway
  validation. See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Contents

- `configs/baseline.json`: preserved live baseline; never edited by the harness.
- `configs/candidates.json`: review-only, one-factor experimental alternatives.
- `configs/workloads.json`: staged test matrix, not an executable job queue.
- `tests/`: inventory, profile inspection, benchmarks, interface checks, offline tests.
- `tests/prefill_diagnostic.py`: separately approved, fixed two-request scheduling
  observation; not a no-queue performance benchmark. See `docs/PREFILL_DIAGNOSTIC.md`.
- `tests/scheduled_benchmark.py`: separately approved bounded 32K scheduling-aware
  screening; not strict no-queue qualification. See `docs/SCHEDULED_SCREENING.md`.
- `evidence/`: timestamped inventories and future experiment reports.
- `docs/`: runbook, experiment order, methodology, and results history.

This is a local workspace. No remote repository is created or pushed. Review
environment-specific metadata and licensing before any future publication.
