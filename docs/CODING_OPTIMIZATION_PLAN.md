# Coding-workload optimization plan

The operator reports that this model is used mostly for coding and asked to start
with HiCache compatibility research and a speculative-decoding comparison. This plan
keeps the live `memory-088` service unchanged; it does not authorize a restart or
inference run.

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
confound a comparison with the running 0.88 candidate. The new offline profile
`memory-088-mtp-off` holds memory fraction at 0.88 and removes the four speculative
launch settings. Compare it serially against `memory-088`; never run both full
candidates together. Record effective capacity, input limit, admission cap and
hybrid-state allocation because disabling speculation can change them automatically.

For a coding-focused comparison, use fixed repository/code-edit prompts rather than
the synthetic archive/retrieval prompt. Choose context and completion sizes from the
real coding traffic; compare TTFT, per-user completion latency, generated tokens/s,
and the available per-request speculation acceptance metadata. Keep prompts and
sampling identical across profiles, and review code outputs for correctness rather
than treating token throughput as coding quality.

**Before a live comparison:** settle the representative coding prompt/output sizes,
capture fresh preflight, obtain an approved idle window, and use the harness's live
confirmation flags. No live configuration or service state was changed during this
offline preparation.
