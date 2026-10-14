# Experiment order and candidate status

All candidates are **unapplied and unvalidated**. Preliminary short-input baseline
measurements and two scoped retrieval checks are now recorded in `results.md`.
Post-reboot short c1/c2/c4/c6 cold and two-pass warm screening passed; post-reboot
32K c1 cold/warm retrieval and cold/warm decode passed too. Strict no-queue 32K
c2 cold screening stopped after observing one waiting request; remaining concurrency
and larger-context throughput tests were paused. A separate one-round diagnostic
supported transient prefill waiting. Subsequently approved scheduling-aware 32K
screening completed c2/c4/c6 cold and warm. The initial c6 warm invocation remains
excluded after unrelated traffic; a separately approved retry passed under a fresh
best-effort quiet window. The baseline screening stage is complete. Separate
100K and 200K c1 cold retrieval screens passed after their own preflight/approval;
the first 100K preflight was blocked and retained. Any 260K or higher-load test
requires separate approval. See `LONG_CONTEXT_100K.md` and `LONG_CONTEXT_200K.md`.
Keep pre/post-reboot
results separate because cached checkpoint metadata changed.
`configs/workloads.json` describes the intended screening matrix; do not run the
full cross-product unattended.

## Stage 1: unchanged baseline

1. Interface smoke checks: chat, separated reasoning, synthetic function call.
2. Short input (1,024 then 32,768 tokens), outputs 256 and 1,024, concurrency
   1 / 2 / 4 / 6, independently recorded cold and warmed cache states.
3. Retrieval checks at increasing prompt lengths, then matched decode timings.
4. Prompts 100,000 and 200,000 tokens at concurrency 1 / 2 / 4 / 6.
5. With separate approval: one 260,000-token prompt, then six 230,000-token
   prompts, each reserving 1,024 output tokens. Both fit the baseline 90% pool
   guard, but have not been live tested and may expose other limits.

## Stage 2: one factor at a time, relative to baseline

| Profile | Only experimental factor | Caveat |
|---|---|---|
| `admission-6` | `--max-running-requests 6` | No claim that six full contexts fit safely; does not accelerate a c6 workload by itself |
| `mtp-off` | Remove the four speculative settings | Automatic active-request cap, usable input limit, graphs, hybrid-state allocation and token capacity can change |
| `mtp-shallow` | One step / two draft tokens | Coupled flags describe one draft-depth factor; actual draft acceptance must be observed |
| `prefill-4096` | Chunk 4,096 | Compare TTFT and decode responsiveness, not only throughput |
| `prefill-16384` | Chunk 16,384 | Larger workspace/prefill pauses possible |
| `memory-088` | Static fraction 0.88 | High risk; current process GPUs are nearly full, and this must replace, not coexist with, baseline |
| `metrics-on` | Enable metrics | An observability control, not an optimization; remeasure separately |

Source inspection confirms the existing image declares these options. No parser
normalization, startup, kernel, allocation or runtime compatibility test has been
performed for the candidates. Profile inspection is offline argument manipulation,
not a successful SGLang startup check.

The memory candidate stops at 0.88; only consider 0.90 if measurements demonstrate
headroom and 0.88 passes. Recompute the workload budget from each live candidate's
actual capacity. Do not compare an isolated flag's effect without accounting for
SGLang's automatic effective-setting changes.

## Deferred, not configured for deployment

- Explicit FP8 KV and other KV dtypes: CLI support alone is insufficient for this
  model's full/linear attention combination, FlashInfer kernels, and speculation.
- DP-attention, HiCache, alternative attention backends: require hybrid-state/cache
  compatibility investigation; H200 GLM evidence does not qualify them here.
- More than six concurrent requests on short contexts: staged after baseline.
- Sustained load, queue saturation, overload/retries, per-user fairness and affinity.
- Coding/agent quality and end-to-end behavior through the real gateway/client.

Choose a winner based on useful concurrency, latency, correctness, stability and
capacity together. Combine independently promising factors only in a new, explicit
follow-up profile, then rerun the complete validation sequence.
