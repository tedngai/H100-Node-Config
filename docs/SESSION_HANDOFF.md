# Session handoff — coding optimization

**Updated:** 2026-10-16, after the third MTP-off startup was blocked and MTP-on restored.
This is the current resume point for a new session.

## State at handoff

- Current candidate: `sglang-qwen38-flash-next-088`, **running** on the original
  0.88 configuration. It was restored after the temporary off-profile attempt and
  verified ready/idle at `20261016T004713Z`. It is the only inference candidate that
  should be running.
- Original baseline `sglang-qwen38-flash-next`: **stopped and preserved**. Do not
  modify `configs/baseline.json`.
- Temporary off containers are stopped and preserved; do not remove them without
  explicit approval:
  - `sglang-qwen38-flash-next-088-mtp-off` — failed prestart argv check; never started.
  - `sglang-qwen38-flash-next-088-mtp-off-coding` — started without inference, but
    effective attention backend was FA3 rather than FlashInfer; stopped.
  - `sglang-qwen38-flash-next-088-mtp-off-coding-20261015T2141` — matched
    argv/image/runtime (with one documented Docker default normalization), started
    and verified with FlashInfer and speculation off;
    **no MTP-off inference was sent**. It is stopped and preserved after its active
    cap was null in the top-level field (the then-current harness did not yet consume
    the explicit per-DP metric) and an access audit found unaccounted chat/API
    traffic. Do not remove it.
- HiCache remains **disabled**. No cache flush or HiCache workload was performed.
- Three off-startup attempts and their restoration audits repeatedly recorded one
  `POST /v1/chat/completions` and one `[other-route]` GET that were not sent by this
  harness. `/v1/loads` was idle at sampled checks, but route isolation has not been
  established. **Do not switch profiles or send inference until the source is paused
  or isolated and a fresh preflight passes.**

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

## Completed coding MTP-on arm

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
- The report captures code answers for review but does not execute or automatically
  score them.

Primary evidence:

- `evidence/coding-mtp-ab-on-64k-2k-20261015T203242.938021Z.json`
- `evidence/coding-mtp-ab-on-final-audit-20261015T203508.607365Z.json`
- `evidence/coding-mtp-ab-prompt-match-20261015T204759.134735Z.json`

The latest retry is documented in
`evidence/coding-mtp-ab-off-startup-preflight-finaltry-20261016T004409.479664Z.json`
and `evidence/coding-mtp-ab-on-restored-after-off-20261016T004713.382186Z.json`.
The MTP-off benchmark was not run; the earlier 64K/2K MTP-on result remains the only
coding arm. The latest on-arm preflight passed, and the off profile's capacity and
explicit DP1 cap checks passed, but its startup audit again found one chat completion
POST and one unknown GET. No harness inference request was sent. The original MTP-on
candidate was restored ready/idle.

## Resume procedure

1. Identify and pause/isolate the client or gateway producing the chat POST and
   unknown route. Obtain explicit confirmation of that source isolation; prior quiet-
   window confirmations and idle samples were insufficient.
2. Run a fresh sanitized inventory and preflight on the restored 0.88 MTP-on
   candidate. Stop if any unrelated route or inference appears.
3. Re-resolve `python3 -B tests/profiles.py memory-088-mtp-off` and verify the
   preserved stopped candidate
   `sglang-qwen38-flash-next-088-mtp-off-coding-20261015T2141`. Start it serially
   only after the fresh MTP-on preflight passes. Verify exact argv/image and runtime
   equivalence (including the documented Docker default normalization), readiness,
   FlashInfer, speculation disabled, and the explicit per-DP request cap **before
   inference**. Record effective capacity, input limit, admission and hybrid-state
   changes.
4. If startup/profile checks fail, or if any unrelated traffic appears, send no
   inference; wait for idle, stop the temporary candidate, restore and verify
   `memory-088`, and retain timestamped evidence. Do not remove containers.
5. If preflight passes, run only the approved matched off arm: same 64K/2K, c6,
   three rounds, cold mode, seed `20261015`, prompt set `coding-mtp-ab-v1`; verify
   hashes match. Use `--execute --confirm-idle`. Review exact traffic, OOM/retractions,
   effective configuration, per-request latency, throughput, and speculation
   metadata.
6. Restore and verify `sglang-qwen38-flash-next-088` after the arm. Do not leave the
   off candidate as the serving profile without a separate decision.

The harness suite passes **106 tests** after adding support for SGLang's explicit
per-DP effective request-cap metric. The MTP-off A/B is still incomplete. Follow
`/home/tngai/H100-Node-Config/AGENTS.md`: no live changes without explicit approval,
preserve timestamped evidence, run the harness suite after harness changes, and
commit/push intended updates by default.
