# Session handoff — coding optimization

**Updated:** 2026-10-15, after the coding MTP-on arm and blocked MTP-off preflight.
This is the current resume point for a new session.

## State at handoff

- Current candidate: `sglang-qwen38-flash-next-088`, **running** on the original
  0.88 configuration. It was restored after the temporary off-profile attempt and
  verified ready/idle at `20261015T204514Z`. It is the only inference candidate that
  should be running.
- Original baseline `sglang-qwen38-flash-next`: **stopped and preserved**. Do not
  modify `configs/baseline.json`.
- Temporary off containers are stopped and preserved; do not remove them without
  explicit approval:
  - `sglang-qwen38-flash-next-088-mtp-off` — failed prestart argv check; never started.
  - `sglang-qwen38-flash-next-088-mtp-off-coding` — started without inference, but
    effective attention backend was FA3 rather than FlashInfer; stopped.
- HiCache remains **disabled**. No cache flush or HiCache workload was performed.
- The most recent preflight found unrelated API traffic even though `/v1/loads` was
  idle. The previous quiet window is no longer valid. **Do not switch profiles or
  send inference until the operator reconfirms an isolated window and a fresh
  preflight passes.**

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
  backend, and removes the four speculative launch flags. An initial off startup
  auto-selected FA3; that mismatch was caught before inference. The revised profile
  has **not** yet been started.

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

The preflight that blocked the off arm is
`evidence/coding-mtp-ab-before-off-preflight-20261015T204842.080907Z.json`. It
recorded one `POST /v1/chat/completions` and one `[other-route]` GET after restore;
no off-arm inference was sent.

## Resume procedure

1. Get a **new explicit quiet-window confirmation** and coordinate isolation of the
   chat/API clients. Do not infer quiet from the last idle `/v1/loads` sample.
2. Run a fresh sanitized inventory and preflight on the restored 0.88 MTP-on
   candidate. Stop if any unrelated route or inference appears.
3. Resolve and review `python3 -B tests/profiles.py memory-088-mtp-off`. Build a new
   temporary container from the pinned image and captured runtime settings, with the
   exact profile argv. Verify its argv, readiness, effective `mem_fraction_static`
   0.88, `attention_backend` FlashInfer, and speculation disabled **before sending
   any inference**. Record automatic capacity/admission/hybrid-state changes.
4. If startup or profile checks fail, send no inference; stop the temporary candidate
   only when idle, restore the preserved `memory-088` container, and save the failed
   probe in a new timestamped evidence file. Do not remove containers.
5. If preflight passes, run only the approved matched off arm: same 64K/2K, c6,
   three rounds, cold mode, seed `20261015`, prompt set `coding-mtp-ab-v1`; verify
   hashes match. Use `--execute --confirm-idle`. Review exact traffic, OOM/retractions,
   effective configuration, per-request latency, throughput, and speculation
   metadata.
6. Restore and verify `sglang-qwen38-flash-next-088` after the arm. Do not leave the
   off candidate as the serving profile without a separate decision.

The latest harness suite passed **102 tests**. Changes and evidence are pushed on
`main` through commit `545e243`; the tree was clean and remote `main` matched at
handoff. Follow `/home/tngai/H100-Node-Config/AGENTS.md`: no live changes without
explicit approval, preserve timestamped evidence, run the harness suite after harness
changes, and commit/push intended updates by default.
