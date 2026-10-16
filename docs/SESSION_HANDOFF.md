# Session handoff — coding optimization

**Updated:** 2026-10-16, after the matched MTP-off arm completed and MTP-on was restored.
This is the current resume point for a new session.

## State at handoff

- Current candidate: `sglang-qwen38-flash-next-088`, **running** on the original
  0.88 configuration. It was restored after the off arm and verified ready/idle at
  `20261016T011253Z`. It is the only inference candidate that
  should be running.
- Original baseline `sglang-qwen38-flash-next`: **stopped and preserved**. Do not
  modify `configs/baseline.json`.
- Temporary off containers are stopped and preserved; do not remove them without
  explicit approval:
  - `sglang-qwen38-flash-next-088-mtp-off` — failed prestart argv check; never started.
  - `sglang-qwen38-flash-next-088-mtp-off-coding` — started without inference, but
    effective attention backend was FA3 rather than FlashInfer; stopped.
  - `sglang-qwen38-flash-next-088-mtp-off-coding-20261015T2141` — matched
    argv/image/runtime (with one documented Docker default normalization), completed
    the matched MTP-off arm, and is now stopped and preserved. Do not remove it.
- HiCache remains **disabled**. No cache flush or HiCache workload was performed.
- The previously flagged startup `GET /model_info` and `POST /v1/chat/completions`
  are SGLang's local warmup sequence: both came from loopback, in that order, before
  the ready marker. They were not external client traffic. The request-audit parser
  now recognizes `/model_info`; benchmark-window auditing still requires exact
  inference-request counts.

## Configuration facts

- Live argv uses `--speculative-algorithm NEXTN`, three steps, top-k 1 and four draft
  tokens. The effective SGLang field is `speculative_algorithm: EAGLE`; for this
  Qwen4-Exp checkpoint, NEXTN is its model-internal MTP draft path. Speculation is on.
- HiCache compatibility is promising, not proven for this exact checkpoint. The
  pinned build has a hybrid full-KV/Mamba host-cache path, and its Qwen3.5 HiCache
  test uses four H100s and the same NEXTN 3-step/top-k-1/four-token shape. Keep
  HiCache disabled until a separately approved startup and verified hybrid-state
  restore. A previous host snapshot showed 503 GiB total / 412 GiB available RAM;
  use a deliberately bounded host tier if that branch is later approved.
- The matched candidate is `memory-088-mtp-off` in `configs/candidates.json`. It
  holds memory fraction at 0.88, pins the live arm's effective FlashInfer attention
  backend, and removes the four speculative launch flags. The first off startup
  auto-selected FA3 and was stopped before inference. The revised profile then
  started correctly: effective memory fraction 0.88, attention backend FlashInfer,
  and speculation disabled. Its pool capacity was 1,536,000 slots (versus 1,717,184
  on the MTP-on arm). Top-level `max_running_requests` was null, while the explicit
  SGLang per-DP effective-limit metric was 245. The offline harness now uses that
  explicit DP1 metric when the top-level field is missing; it never sums duplicate
  TP values. Revalidate this metric on each startup.

## Completed matched coding MTP A/B

Workload: six fixed code-edit prompts from the local harness source, **64,000 input
tokens**, natural completion with a **2,048-token cap**, six concurrent users, three
cold synchronized rounds. The prompt context is pinned to
`2449a5575bd7ef7259fa81fcc644ab00c94c09b5`; all 18 prompt hashes were reproduced
exactly for the planned off arm. This is a coding proxy against this harness, not a
qualification of the operator's production code tasks.

- **18/18** completed; each reached the 2,048-token cap.
- Median aggregate output throughput: **529.76 tok/s**.
- TTFT p50: **7.32 s**; latency p50: **22.98 s**. p95 omitted at n=18.
- Mean speculative acceptance rate: **59.4%**; mean acceptance length: **2.78**.
- No observed OOM or retractions; sampled running reached 6 and waiting peaked at 5.

Matched MTP-off arm (same 64K input / 2K cap, c6, three cold rounds, seed, and
`coding-mtp-ab-v1` prompt hashes):

- **18/18** completed; each reached the 2,048-token cap.
- Median aggregate output throughput: **403.39 tok/s**; TTFT p50 **9.83 s**;
  latency p50 **30.44 s**. p95 omitted at n=18.
- Relative to MTP-on, aggregate throughput was **23.9% lower**; TTFT p50 and latency
  p50 were **34.2%** and **32.5% higher**, respectively.
- No observed OOM or retractions. Queueing and sampled free GPU memory below the
  advisory warning threshold were recorded; neither failed the capacity policy.
- Outputs are captured for manual code review; they are not executed or automatically
  quality-scored. This synthetic proxy is not production qualification.

Primary evidence:

- MTP-on benchmark: `evidence/coding-mtp-ab-on-64k-2k-20261015T203242.938021Z.json`
- MTP-off benchmark: `evidence/coding-mtp-ab-off-64k-2k-resume-20261016T010602.359746Z.json`
- Matched prompt hashes: `evidence/coding-mtp-ab-prompt-match-20261015T204759.134735Z.json`
- Off final traffic/idle gate: `evidence/coding-mtp-ab-off-final-audit-resume-20261016T010909.097840Z.json`
- Restored service verification: `evidence/coding-mtp-ab-on-final-restore-verification-20261016T011253.932370Z.json`

## Follow-up guardrails

The operator approved an **offline allocation investigation only** after the A/B.
See [`MAMBA_KV_ALLOCATION.md`](MAMBA_KV_ALLOCATION.md) for the source-traced
Mamba/scratch allocation explanation and the undeployed `memory-088-mamba-070`
proposal. Its estimated shared-token gain is about 5.2%; this is not measured live.
No service changes or inference were performed for that investigation.

The matched A/B is complete. Any repeat, additional coding workload, deployment, or
cache experiment needs its own explicit approval and fresh preflight. Keep the
MTP-on candidate as the serving profile; the stopped off candidate and original
baseline are preserved.

The harness suite passes **108 tests**, including the explicit per-DP effective
request-cap fallback, `/model_info` route classification, and ratio-only candidate
isolation. Follow
`/home/tngai/H100-Node-Config/AGENTS.md`: no live changes without explicit approval,
preserve timestamped evidence, run the harness suite after harness changes, and
commit/push intended updates by default.
