# Six-user long-context configuration optimization plan

**Acceptance-policy update:** new runs use [capacity-first policy](BENCHMARK_POLICY.md),
not mandatory no-queue/fixed-prefill-window/3 GiB-floor screening. The 0.88 c6 cold
100K/512 and separately approved 200K/512, 230K/512, 250K/512, 250K/4096 and
256K/512 screens passed with no observed OOM; a five-round 250K/4096 repeat also
completed 30 requests. The topology/workload ideas below remain proposals, not
automatic authorization.

## Status and objective

Planning only, requested on 2026-10-15. This document does not authorize inference,
service changes, cache operations, package installation, or deployment. Existing
baseline results remain unchanged; no proposed configuration is qualified.

**Priority correction:** first answer the memory-fraction capacity/risk question,
before pursuing the broader architecture matrix. See
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md) for the read-only 0.88/0.90
estimate and staged memory-only qualification plan. Test 0.88 before considering
0.90; no live change is approved by this planning request.

Optimize for **six realistic concurrent users**, preserving useful long contexts
and conversational responsiveness. More than six is a secondary headroom probe,
not the primary optimization target. Prioritize usable capacity and worst-user
experience over isolated c1 throughput or an advertised maximum request count.

Working interpretation: approximately **1.5 million aggregate active context
tokens**, not 1.5M per request. The per-request context remains 262,144 including
output unless separately investigated. Confirm acceptable TTFT, inter-token
latency, and whether all six users must simultaneously approach the context limit
before final acceptance criteria are fixed.

## 1. Capacity accounting: establish what the numbers mean

Baseline: four H100 80GB, TP4 / EP4 / DP1, 1,587,968 shared GPU token slots,
BF16 hybrid state, KV dtype `auto`, static memory fraction 0.85, prefill chunk
8,192, and three-step/four-draft-token speculation. FP8 weights do not imply FP8 KV.

The harness's 90% pool guard permits about **1,429,171 slots**. This is an
experimental safety policy, not a demonstrated SGLang hard limit. Do not relax it
to manufacture a capacity pass. Count output reservations as well as input:

| Independent simultaneous sessions | Fresh token-slot budget | Baseline 90% guard |
|---|---:|---|
| 6 × (100,000 input + 512 output) | 603,072 | Fits arithmetically |
| 6 × (200,000 + 512) | 1,203,072 | Fits arithmetically |
| 6 × (230,000 + 512) | 1,383,072 | Fits arithmetically |
| 6 × (250,000 + 512) | 1,503,072 | Exceeds guard |
| 6 × (256,000 + 512) | 1,539,072 | Exceeds guard |

To reserve six 250K inputs plus 512 outputs inside that guard requires at least
**1,670,080 measured GPU slots**. Six 256K inputs require **1,710,080**. These are
minimum arithmetic targets, not promises about hybrid-state capacity, workspace,
cache fragmentation, or safe sustained operation. Longer outputs need new budgets.

Report separately: per-request context limit; GPU-resident pool per distinct DP
rank; hybrid/Mamba state capacity; CPU-cache capacity; measured peak active
requests; and workload-qualified aggregate occupancy. Never sum duplicate TP
metrics or infer actual active concurrency from client concurrency/token division.
Do not rely on cross-user prefix sharing to pass the independent-context target.

## 2. Phase A — offline feasibility and instrumentation

Before any candidate startup, inspect the **pinned image's actual source/build**,
not just current upstream documentation or CLI flag availability. Record a
compatibility table and implementation references for:

- DP-attention with this model's hybrid full/linear attention, MoE expert layout,
  FlashInfer prefill/decode, Triton verification, and speculation.
- Two independent TP2 replicas: supported TP/EP grouping, model/expert divisibility,
  weight/state footprint, GPU grouping, and router requirements.
- HiCache: supported cache implementation and hybrid-state persistence, host-memory
  sizing, transfer backend, prefix matching, eviction, and compatibility with each
  topology and speculation. Distinguish an unsupported combination from a slow one.
- Explicit lower-precision KV: actual baseline KV dtype, full-attention kernel and
  speculation compatibility, required scaling metadata, and quality risks. Do not
  assume KV quantization also compresses BF16 linear-attention state.
- Existing GPU/host memory evidence and what extra read-only inventory is needed;
  no allocation stress test or weight load is part of offline research.

Prepare a separately reviewed harness extension, with offline regression tests:

- Generalize scheduling-aware long-context tests; do not reuse the fixed 32K
  waiting bound for 200K prompts or weaken the strict benchmark's queue policy.
- Account for each independent DP pool, routing destination, per-rank admission,
  running/waiting metrics, retractions, cache hits, and effective configuration.
- For replicated servers, use explicit endpoint inventories and controlled routing;
  for native DP, verify rank-attributed telemetry and routing observability.
- Distinguish queued sessions from actively serviced requests. If a claimed active
  concurrency or per-rank occupancy cannot be observed, mark it unqualified.
- Add bounded mixed-length/multi-turn workloads and per-user progress/stall timing.
  Missing data is unavailable, not zero; do not save prompts or raw live logs.

DP2 remains blocked until these checks and tests pass. Run
`python3 -B -m unittest discover -s tests -v` after harness changes.

## 3. Phase B — establish the missing six-user baseline

Following a separately approved protocol and idle window, progress from c2 to c4
to c6 at 100K input, then 200K; attempt six 230K sessions only after the lower
stages pass. Use 512 output tokens for initial matched screens, separate retrieval
and decode tests, and three rounds only as screening evidence.

Test three distinct cache/arrival conditions rather than a full cross-product:

1. Independent cold prefixes, synchronized arrivals: admission/prefill pressure.
2. Six independently warmed conversation prefixes: steady decode and cache retention.
3. Staggered multi-turn users: one long prefill while other users decode, growing
   histories, short tool-style turns, and later 2,048-token outputs where budgeted.

For warm cases, warming six sessions must not silently evict earlier ones: record
cache reuse for every timed user, with fixed warmup counts and no rescue retries.
For all stages, explicitly bound initial prefill waiting and time to last user's
first token, record starvation/decode stalls, and stop on sustained/out-of-policy
waiting. Initial waiting is not a strict no-queue pass. Compare equivalent arrival
patterns and cache states across candidates.

This phase establishes whether the existing configuration already meets the actual
six-user requirement and where it fails: memory/state, prefill, decode, or routing.
Do not finish an exhaustive baseline matrix before screening promising candidates.

## 4. Phase C — candidate branches, each relative to original baseline

| Priority / branch | Proposed comparison | Decision it supports |
|---|---|---|
| Early: admission/state | Explicit active cap 6 versus automatic 48 | Does lower admission change graphs/state allocation and usable capacity? It is not itself a speedup. |
| Early: speculation | Off, then shallow versus baseline depth | Can less speculative workspace/state improve six-user capacity or responsiveness without unacceptable decode loss? Record automatic effective changes. |
| Capacity | Static memory fraction 0.88 versus 0.85 | Does measured extra pool capacity justify reduced runtime margin? Only after memory review; no automatic 0.90 escalation. |
| Architecture | DP-attention=2 on four GPUs, exact TP/EP layout determined by source | Can distributed attention and retained expert sharding improve six-user service/capacity? No assumption that capacity doubles. |
| Architecture control | Two independent TP2 replicas, three users per replica | Does reduced collective overhead outweigh duplicated weights and smaller per-replica pools? Feasibility gate first. |
| Reuse | HiCache on baseline topology, then on a separately qualified topology | Does host-tier prefix reuse reduce returning-user TTFT/cache thrash at acceptable RAM/transfer cost? Not presumed active GPU capacity. |
| Conditional capacity | Supported lower-precision KV versus actual baseline dtype | Can resident capacity grow with acceptable retrieval and application quality? Hybrid state may remain the bottleneck. |
| Responsiveness | Prefill chunks 4,096 and 16,384 versus 8,192 | Best worst-user TTFT/decode-stall trade-off under mixed six-user traffic. |

Architecture changes are one topology factor with necessarily coupled TP/DP/EP
settings; document all of them. They are not equivalent to a one-flag comparison.
Keep image/model revision, workload, and unrelated tuning settings fixed. If a
candidate requires disabling speculation or changing image/backend to work, record
that dependency and use a matched control; do not attribute the combined result
solely to DP or HiCache. An image upgrade is its own compatibility branch.

### DP2 interpretation and routing gates

**Two TP2 replicas** duplicate model weights across groups. Baseline reports about
32.2 GiB weight allocation per GPU at TP4; naive TP2 scaling suggests roughly
twice that per GPU, before cache/state/runtime allocations. This is only a rough
feasibility warning, not a fit prediction: duplicated weights may reduce total KV
capacity despite improved throughput. Never launch alongside the current service.

**DP-attention** can use a different expert-sharing layout and must be evaluated
separately; determine the exact supported topology from this build first. Compare
per-rank capacity and both balanced routing (3+3) and uneven routing (4+2). Test
session affinity/cache locality and a returning session routed elsewhere. A summed
pool is not one fungible pool; each assigned session must fit its destination.

### HiCache interpretation and workloads

Treat host memory as a prefix-cache tier unless this exact implementation proves
otherwise. Cached history generally must be usable in GPU execution state before
decode; host storage does not automatically permit six larger active contexts or
extend the model's per-request context limit.

After compatibility passes, measure cold misses, GPU-cache hits, host-cache hits
after **controlled natural eviction**, and multi-turn return after other sessions
run. Verify actual tier hit/restore telemetry; never label a fast return a host hit
without evidence. Measure RAM, transfer volume/latency, eviction and worst-user
TTFT. No cache flush is implied; bound all churn requests in the approved protocol.
If hybrid-state restore is unsupported, stop this branch rather than counting a
full-attention-only hit as complete conversation reuse.

## 5. Common gates, shortlist, and final qualification

For every approved startup: preserve original container/image and baseline file;
test serially, never colocating full candidates; capture sanitized effective
configuration, actual token/state capacity, health, and model identity. Arrange an
explicit rollback procedure/window before stopping the current service. No
startup, restart, rollback execution, or persistent deployment is authorized here.

For each feasible candidate, start with smoke/correctness and short c1, then the
same bounded 32K c6 and 100K c6 reference cases after lower-stage gates. Promote
only promising candidates to the 200K/230K six-user cases. Budget against that
candidate's measured per-pool capacity; a smaller pool means skip, not forced OOM.
Near-250K six-user cases require a candidate that actually passes the guarded
budget and all lower stages. Preserve every failed probe without automatic retry.

Stop on request/error/truncation/token mismatch, recall/interface regression,
retraction, stale/missing required telemetry, unhealthy memory/GPU state,
out-of-policy queueing/stalls, unrelated traffic, or configuration drift. Audit
request counts, fresh idle loads, and identity after every invocation.

Shortlist by this order:

1. Six independent long-context users fit with measured runtime margin and pass
   retrieval, tool/reasoning, and representative application checks.
2. Worst-user responsiveness meets operator-approved TTFT/TPOT/stall limits; all
   users make progress. Report actual active concurrency and aggregate throughput.
3. Capacity headroom, repeat-turn cache behavior, startup/recovery complexity, and
   stability improve enough to justify operational cost.

Combine independently promising factors only in a new reviewed profile. Repeat
matched controls after restoration and perform a separately budgeted sustained
multi-turn run with at least 30 request samples per important workload for an
initial p95 view (not reliable tail qualification by itself). Agree a duration and
request cap before running. Optional c8 testing comes last and must not sacrifice
the six-user objective. Publish a comparison of measured resident capacity,
qualified contexts/users, worst-user latency, throughput, host RAM/cache behavior,
and known limitations. Deployment remains a separate operator decision.

## Immediate next step

Complete Phase A and write the bounded Phase B protocol. Research DP-attention and
HiCache compatibility early so unsupported branches can be removed before any
maintenance window. Do not begin with a blind DP2/HiCache/memory combination or
assume that a reported 1.5M token pool already qualifies six near-limit users.
