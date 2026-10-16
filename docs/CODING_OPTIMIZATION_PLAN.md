# Coding-workload optimization plan

Follow-up: [`MAMBA_KV_ALLOCATION.md`](MAMBA_KV_ALLOCATION.md) explains the MTP-off
capacity loss. After separate deployment/paused-traffic/smoke approval, the MTP-on
ratio-0.7 candidate is serving with 1,806,656 measured shared slots (+5.21%). Startup
and interface smoke passed; its coding/long-context performance is not yet measured.

The operator reports that this model is used mostly for coding and asked to start
with HiCache compatibility research and a speculative-decoding comparison. The
matched live A/B was approved and completed on 2026-10-16. Both arms passed 18/18;
MTP-on was faster on this synthetic coding workload. Both comparison arms used ratio
0.9; the original MTP-on service was restored afterward and is now preserved/stopped
as the ratio-0.7 deployment's rollback target. See the measured comparison below and timestamped evidence in
`results.md`.

## Current serving configuration

The captured launch argv uses `--speculative-algorithm NEXTN`, three speculative
steps, top-k 1 and four draft tokens. The effective server configuration reports
`speculative_algorithm: EAGLE` and the same checkpoint as its draft path. The pinned
SGLang source identifies Qwen4-Exp's NEXTN draft layer as model-internal MTP. In
other words, speculation is on; the effective backend name should not be mistaken
for the absence of Qwen's NEXTN/MTP draft.

In the latest 60-request capacity run, per-request metadata reported mean
`spec_accept_rate` **0.616** and mean `spec_accept_length` **2.846**. This is useful
evidence that draft tokens are being accepted on the synthetic long-context workload,
but it is not a speedup comparison and does not predict coding-prompt acceptance.

## Offline HiCache compatibility finding

The exact pinned SGLang build (`d91c3682b0b429e4c70df63cd57f819588ce29b0`) contains
a unified-cache route for hybrid SSM models and a HiCache stack with distinct full-KV
and Mamba host pools, backup, prefetch and load-back paths. Its registered Qwen3.5
HiCache test uses four H100s and NEXTN with three steps, top-k 1 and four draft
tokens. This is a strong compatibility signal for the same model family and draft
shape, not proof for this exact Qwen3.8-Flash-Next checkpoint/build combination.

The latest host snapshot showed **412 GiB available RAM**; the container has no
configured memory limit. If pursued, size the host tier deliberately and account for
other host workloads—do not blindly use the test's 2x pool ratio. First gate on a
separate candidate startup and verified hybrid-state host restore. HiCache remains
disabled on the live service.

## Matched speculation-off candidate

The existing `mtp-off` profile inherits baseline memory fraction 0.85 and would
confound a comparison with the running 0.88 candidate. An initial off-profile startup
also auto-selected FA3 instead of the on arm's FlashInfer backend, so it was stopped
without inference. The matched `memory-088-mtp-off` profile now pins memory fraction
at 0.88 and FlashInfer, while removing the four speculative launch settings. Compare
it serially against `memory-088`; never run both full candidates together. Record
effective capacity, input limit, admission cap and hybrid-state allocation because
disabling speculation can change them automatically.

The operator selected **64K prompt / 2K maximum output**, six concurrent users and
three rounds per profile. The offline harness now builds six fixed code-edit prompts
from the exact local harness source snapshot `2449a5575bd7ef7259fa81fcc644ab00c94c09b5`,
uses natural EOS (2K is a cap), and stores outputs for review. Use
`--prompt-set-id coding-mtp-ab-v1`, the same seed and other workload flags in both
arms; verify prompt hashes match. Compare TTFT, per-user completion latency, generated
tokens/s, and per-request speculation acceptance. Review code outputs for correctness
rather than treating token throughput as coding quality.

**Live comparison result:** the approved 64K/2K, c6, three-cold-round comparison
completed with matched `coding-mtp-ab-v1` prompts (18 requests per arm). MTP-on
median aggregate throughput was **529.76 tok/s**, TTFT p50 **7.32 s**, and latency
p50 **22.98 s**. MTP-off measured **403.39 tok/s**, TTFT p50 **9.83 s**, and latency
p50 **30.44 s**: aggregate throughput was **23.9% lower** with MTP disabled. Both
arms completed all requests at the 2,048-token cap without observed OOM or
retractions. Queueing and sampled free GPU memory below the advisory warning level
were recorded; p95 is unavailable at n=18. The generated code answers require manual
review and were not automatically quality-scored.

The matched off profile held memory fraction at 0.88, pinned FlashInfer, and disabled
speculation. Effective pool capacity was **1,536,000** slots (on arm: **1,717,184**).
Although top-level `max_running_requests` was null, SGLang explicitly reported the
per-DP effective cap **245**; the harness uses that direct DP1 metric and never sums
duplicate TP values. Earlier startup audits' loopback `GET /model_info` and
`POST /v1/chat/completions` were SGLang's own warmup sequence before its ready marker,
not external client traffic. No unrelated route appeared in the benchmark window.
The off candidate remains stopped/preserved. The original MTP-on ratio-0.9 candidate
was restored after the A/B, then stopped/preserved for the separately approved
ratio-0.7 deployment. See `SESSION_HANDOFF.md` and `results.md` for current state,
evidence, and limitations.
