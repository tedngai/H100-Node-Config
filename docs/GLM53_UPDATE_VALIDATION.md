# GLM update maintenance validation — 2026-10-31

**Validation in progress; candidate not promoted.** The operator explicitly
approved a maintenance window for live candidate validation. The recorded
production profile remains unchanged. During the window, the isolated candidate
temporarily serves the same model ID/port with restart policy `no`; the old GLM
container/image are stopped and preserved, not removed.

## Compared configuration

Both builds use TensorFold v0.6.0, the same pinned model and DFlash2 revisions,
TP4/NCCL on four H100s, four streams, context 1,048,576, pool 4,345,856 tokens,
q4 dense / fp8 KV, DFlash2, vision/thinking enabled, 22.5 GiB pool cap and 5 GiB
reserve. No optional Spark tuning, spill, prefix wait or KV sharding was enabled.

- Old image: `sha256:b8f133b98c0976158bd8b2218286be7968474a88bf776dbf1d7448a5101aeb1a`.
- Candidate: `sha256:09cb4a76ca5ee2080c3f50bca7985c904c5b48f741f61940ffa734d35ffe179c`.
- Candidate recipe commit/hash: `bf5f945` / `789e8f3bdfa2` (123 patches).
- Build and CPU evidence: [candidate build record](GLM53_CANDIDATE_BUILD.md).

The old bind-mounted entrypoint's non-idempotent device patch was repaired while
stopped, with original inputs/logs preserved privately outside this repository.
A real old-container restart passed in 201.335 s with the original pool/context,
followed by chat, reasoning, tool and vision smoke. Existing unrelated deployment
script/config changes were preserved. No rollback container/image was deleted.

The first candidate preflight refused recently closed `TIME_WAIT` sockets despite
no active listeners. The probe now uses `SO_REUSEADDR` and `listen`, not
`SO_REUSEPORT`; an offline test verifies that actual listeners remain refused.
The failed preflight is retained in evidence. The first candidate GPU boot then
passed, including cold kernel compilation, in approximately 653 seconds.

## Passed interface / agent checks

- Chat, separated reasoning, synthetic tool call and synthetic colour vision.
- Anthropic streaming text, positive prompt usage at stream head, clean termination.
- OpenAI Responses text route.
- Quoted `<think>`, `</think>`, `<tool_call>` and role markers round-trip through
  JSON-schema-constrained output without spurious tool calls.
- Synthetic tool call followed by a tool result containing quoted markup, then
  the correct answer with no additional call. No real tool is executed.
- Cached multi-turn continuation and client-close streaming cancellation back to idle.

See `evidence/glm53-update-new-smoke-20261031T132532.956860Z.json` and
`evidence/glm53-update-new-agent-api-20261031T132537.969214Z.json`.

## Bounded short performance screens

Approximately 1,024 input tokens, 256 forced output tokens per request. Values
below are **median wall-clock aggregate output tok/s**, including prefill/TTFT,
not the sum of request decode rates. Three rounds except the candidate c4 cold
repeat (five). Sampled runs explicitly use temperature 1 / top-p 0.95; others use
temperature 0. No unexpected request-counter deltas were observed.

| Workload | Old | Candidate | Change |
|---|---:|---:|---:|
| c1 cold greedy | 174.0 | 175.5 | +0.8% |
| c4 cold greedy, repeat | 365.6 | 360.8 | -1.3% |
| c4 warm greedy | 451.8 | 456.8 | +1.1% |
| c1 cold sampled | 154.7 | 167.6 | +8.3% |
| c4 cold sampled | 350.4 | 334.1 | -4.6% |

The first candidate cold c4 screen was 319.5 (-12.6%); its three rounds were
316.6, 319.5 and 363.2. Investigation retained that result and repeated five
rounds: 360.8, 371.7, 358.1, 360.7 and 387.1. The large slowdown was not sustained.
Do not infer statistical significance or a general speedup from these screens.
Prompts are freshly marked cold requests, not byte-identical outputs across builds.
The initial old screens also predate the added low-rate GPU-memory sampler.

## Long-context / lifecycle qualification

- 32K retrieval: all three access codes found in all three rounds; median TTFT
  4.404 s (`glm53-update-new-32k-retrieval-20261031T132653.268762Z.json`).
- Native-context, mixed long-prefill/stream continuity and real candidate restart:
  results not yet recorded in this document.

All 17 CPU checks and 145 offline repository tests pass. CPU checks do not replace
GPU validation. Bounded screens do not qualify sustained traffic, p95/p99,
four simultaneous 1M requests, workload-wide coding quality or external gateways.
No permanent production promotion or performance improvement is claimed.
