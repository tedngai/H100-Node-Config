# Experiment order and candidate status

New benchmarks follow [capacity-first policy](BENCHMARK_POLICY.md), not mandatory
zero-queue or fixed-prefill-duration screening. Previous evidence retains its
original policies and verdicts. No candidate deployment is implied by this rewrite.

The next planning priority is six-user long-context capacity and responsiveness;
see [`SIX_USER_CAPACITY_PLAN.md`](SIX_USER_CAPACITY_PLAN.md) for staged baseline,
DP2, HiCache, memory/state, and final qualification branches. Proposed branches
remain unqualified and require their own compatibility checks and approvals.

**Live candidate (2026-10-16, 02:14 UTC):** `memory-088-mamba-070` is now serving
following separate deployment/maintenance-window approval. Measured shared tokens
are **1,806,656**, Mamba state slots **570**, admission **48**, context **262,144**.
Startup and all three interface smoke cases passed; no throughput/long-context
benchmark or cache flush was included. The previous ratio-0.9 `memory-088` container
is stopped/preserved for rollback. See `MAMBA_KV_ALLOCATION.md` and `SESSION_HANDOFF.md`.

**Previous candidate:** `memory-088` was operator-authorized and started on 2026-10-15.
It reports 1,717,184 slots and passed startup, smoke, and initial 32K c1 decode.
Capacity-first c6 cold 100K, 200K, 230K, 250K/512, 250K/4096 and 256K/512 screens
passed without observed OOM; 250K/4096 repeats passed at five rounds (30 requests)
and ten rounds (60 requests), both synchronized and with one-second staggered starts.
Those ratio-0.9 results do not qualify the new ratio-0.7 profile. Production/universal
OOM safety remains unqualified; other planned branches remain unapplied.
The original container is preserved and stopped. See `MEMORY_FRACTION_FIRST.md`.

The separately approved coding MTP-on/off comparison completed on 2026-10-16. Both
64K/2K c6 arms passed 18/18 matched cold requests. Median aggregate throughput was
529.76 tok/s on MTP-on and 403.39 tok/s with MTP disabled; off-arm TTFT and latency
were also higher. No OOM or retractions were observed; queueing and low sampled free
GPU memory were advisory warnings. The startup chat POST and `/model_info` GET were
confirmed as SGLang's local warmup before readiness, not unrelated traffic. MTP-on was
restored after that A/B; the off candidate remains stopped and preserved. See
`CODING_OPTIMIZATION_PLAN.md`, `SESSION_HANDOFF.md`, and `results.md`.

Preliminary short-input baseline
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
the first 100K preflight was blocked and retained. The separately approved 260K c1
near-limit cold retrieval screen also passed. Any repeat, full-context or higher-load
test requires separate approval. Separately approved 100K and 200K c1 cold/warm
decode screens also passed. Any higher-context decode or higher concurrency needs
its own protocol/approval. See `LONG_CONTEXT_100K.md`, `LONG_CONTEXT_200K.md`,
`LONG_CONTEXT_260K.md`, `LONG_CONTEXT_DECODE_100K.md`, and
`LONG_CONTEXT_DECODE_200K.md`.
Keep pre/post-reboot
results separate because cached checkpoint metadata changed.
`configs/workloads.json` describes the intended screening matrix; do not run the
full cross-product unattended.

## Stage 1: unchanged baseline

1. Interface smoke checks: chat, separated reasoning, synthetic function call.
2. Short input (1,024 then 32,768 tokens), outputs 256 and 1,024, concurrency
   1 / 2 / 4 / 6, independently recorded cold and warmed cache states.
3. Retrieval checks at increasing prompt lengths, then matched decode timings.
4. Prompts 100,000 and 200,000 tokens at concurrency 1 / 2 / 4 / 6; a separately
   approved single-session 260,000-token synthetic retrieval screen is recorded.
5. With separate protocol and approval: full 262K or multi-session long-context
   checks. Six 230,000-token prompts with 1,024 output tokens each fit the baseline
   90% pool guard arithmetically, but have not been live tested and may expose other
   limits.

## Stage 2: one factor at a time, relative to baseline

| Profile | Only experimental factor | Caveat |
|---|---|---|
| `admission-6` | `--max-running-requests 6` | No claim that six full contexts fit safely; does not accelerate a c6 workload by itself |
| `mtp-off` | Remove the four speculative settings | Automatic active-request cap, usable input limit, graphs, hybrid-state allocation and token capacity can change |
| `memory-088-mtp-off` | Speculation off, matched against `memory-088` at 0.88 and FlashInfer | Use this profile for a fair live A/B; `mtp-off` above inherits baseline 0.85 and is not a matched comparison |
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
