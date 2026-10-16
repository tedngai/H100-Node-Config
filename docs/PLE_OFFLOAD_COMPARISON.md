# PLE offload comparison — completed 2026-10-16

## Result: already enabled; matched comparison passed and service restored

The operator separately approved a paused-traffic window, temporary PLE-on/off
container changes, bounded benchmarks, and restoration. The live API reported
`ple_offload_embedding: true` **before** any change. The pinned build enables it
automatically; the model constructor uses `device="cpu", pin_memory=True` for
the PLE table. Placement is established from the effective flag and source path,
not direct introspection of live tensors. The earlier ratio-0.7 speed screens thus
were not evidence of a deliberately PLE-disabled baseline.

The approved comparison held ratio **0.7**, static memory **0.88**, MTP, image,
source fingerprints, runtime configuration and other launch settings fixed. The
temporary arm added only `--no-ple-offload-embedding`. Each arm completed **21/21**
timed requests at 32,768 input / 512 output: three c1 requests and 18 c6 requests.
All 21 paired prompt hashes matched; every request reported zero cached tokens.

| Client concurrency | PLE-on decode estimate per request | PLE-off decode estimate per request | PLE-on change versus off | PLE-on / off end-to-end speed per request |
|---:|---:|---:|---:|---:|
| 1 | 265.45 tok/s | 286.49 tok/s | -7.34% | 175.90 / 182.79 tok/s |
| 6 | 111.31 tok/s | 104.51 tok/s | +6.51% | 61.50 / 61.17 tok/s |

At c6, median aggregate throughput was **365.60 versus 366.04 tok/s** (on/off),
essentially unchanged in this screen. Per-request decode intervals can overlap
other requests' prefill; they are not pure isolated decode-kernel measurements.
These small sequential on-then-off samples were not counterbalanced. The current
on arm was already running, whereas the off arm started fresh. Do not interpret
the mixed speed deltas as a reliable general speedup or slowdown.

| Startup measurement | PLE on | PLE off |
|---|---:|---:|
| Shared token capacity | 1,806,656 | 1,124,800 |
| Mamba state slots | 570 | 375 |
| GPU weight memory, reported rank | 32.201 GiB | 43.857 GiB |
| Direct per-DP request cap | 48 | 48 |

Offloading provided **681,856 more shared tokens (+60.62% versus off)** and reduced
reported GPU weight memory by **11.656 GiB per reported rank**. Do not sum duplicated
TP metrics. Automatic pool/state and CUDA-graph allocations changed; they are
retained in each startup/benchmark report. Most freed memory was allocated to pools,
so sampled free GPU memory remained around 4 GiB in both arms. CUDA pinned host
bytes were unavailable; Linux `Mlocked` is not a measurement of CUDA pinned memory.

No observed OOM or retractions. c6 sampled running reached 6 and waiting reached 5
in both arms. Exact traffic, token accounting, identity/configuration and idle gates
passed. No cache flush, HiCache change, long-context test, warm-retention test or
extra interface smoke inference was performed. Startup warmup was audited separately.

The original PLE-on ratio-0.7 container is restored, ready/idle, with capacity
**1,806,656**, slots **570** and cap **48**. The temporary PLE-off container
`sglang-qwen38-flash-next-088-mamba070-pleoff-20261016t024547` is stopped/preserved.
Original baseline and previous rollback/off containers remain stopped/preserved.

- [Placement discovery](../evidence/ple-placement-discovery-20261016T024552.665353Z.json)
- [Matched comparison, all benchmark/gate links and automatic changes](../evidence/ple-comparison-20261016T025555.308566Z.json)
- [Restoration](../evidence/ple-restoration-20261016T025555.308121Z.json)
- [Final full-traffic, identity/idle verification and derived speed/memory deltas](../evidence/ple-final-verification-20261016T025643.244649Z.json)

## Original baseline and planning notes (historical)

The operator requested preserving a decode-speed baseline before trying PLE host
offload. This document does not authorize a restart, deployment, cache flush, or
additional inference. Confirm a fresh paused-traffic window and exact live scope
before execution. Keep all existing rollback containers and `configs/baseline.json`.

## Existing ratio-0.7 speed baseline

The approved 32,768-input / 512-output cold decode screens already recorded the
first and last stream events with increasing completion-token counts. Offline
derivation gives:

| Client concurrency | Requests | Median per-request decode estimate | Median average TPOT estimate | Median per-request end-to-end speed |
|---:|---:|---:|---:|---:|
| 1 | 3 | 266.91 tok/s | 3.75 ms/token | 175.15 tok/s |
| 6 | 18 | 100.44 tok/s | 9.96 ms/token | 61.52 tok/s |

For each request, divide the completion-token increase after the first counted
event by the elapsed time to the last counted event. Then take the median of those
per-request speeds. Do not divide aggregate throughput by concurrency, or invert
the median TPOT to obtain the median speed (these differ for even sample counts).
Decode timing excludes time before the first counted token event, unlike the
end-to-end metric. Streaming/buffering and speculative multi-token bursts make it
an estimate, not pure kernel throughput or an inter-token latency distribution.
At c6, other requests may still be prefilling during a request's decode interval.
Three rounds screen performance; they do not qualify production tails.

Derived evidence with source-file hashes, per-request intervals and prompt hashes:
[`mamba070-decode-speed-baseline-derived-20261016T023931.287527Z.json`](../evidence/mamba070-decode-speed-baseline-derived-20261016T023931.287527Z.json).
Original reports are unchanged.

## Original prerequisite (now resolved): verify current PLE placement

The saved filtered server configuration does **not** include the effective PLE
offload setting. The argv lacks an explicit PLE flag, but that does not prove it
was disabled: some builds enable it automatically. Inspect the exact pinned build's
default, effective model dtype/configuration and actual table placement before
calling either arm PLE-on or PLE-off. If already enabled, adding the flag is not a
new experimental factor; explain that finding rather than claiming a new benefit.
Capture only allowlisted configuration, placement/size observations and source
fingerprints, never raw logs, Docker inspect output or environment values.

## Matched comparison proposal

1. Verify support in the exact build, host available RAM, pinned-memory/memlock
   requirements, per-rank table ownership and total host allocation. CPU RAM alone
   does not establish acceptable PCIe/NUMA lookup performance.
2. For a PLE placement experiment, hold `mamba_full_memory_ratio=0.7`, static memory
   fraction 0.88, model/image/build, TP4/EP4/DP1, MTP settings, context, attention
   backends and other launch settings fixed. Change only verified PLE placement.
   Preserve the current serving container for rollback. Do not combine this with
   HiCache, generic weight offloading, or a ratio change.
3. After separate approval, run fresh audited reference and candidate screens with
   the same 32,768 input / 512 forced output, c1 then c6, three cold rounds, seed
   `20261016`, temperature zero and synchronized arrivals. Match prompt token IDs
   or hashes using the existing `--prompt-set-id` option with the same fixed value
   in both arms; seed alone is not enough because the default cold namespace changes
   per run. Audit actual cache hits: repeating a prompt namespace can produce reuse
   if an arm is rerun without a fresh process. No cache flush is implied.
4. Capture fresh startup/effective configuration and automatic changes, GPU weight
   memory, shared token capacity, Mamba slots, direct per-DP request cap, GPU free
   memory and host available/pinned memory. Missing metrics remain unavailable.
5. Compare median per-request decode estimates and TPOT as the primary speed
   measurements; also report per-request end-to-end speed, aggregate throughput,
   TTFT, latency, cache hits, sampled running/waiting, retractions, request errors,
   observed OOM and exact traffic audits. Report speed change and KV capacity gain
   separately; no universal speed/memory tradeoff can be inferred from one ratio.
6. Require unchanged identity/configuration within each arm, exact token accounting,
   healthy service and final idle gates. Unexpected traffic or runtime/configuration
   failure stops the comparison. Queueing and low GPU-free memory remain advisory
   under the capacity-first policy. Agree restoration/leave-serving behavior before
   starting; a successful screen does not itself authorize permanent deployment.

To isolate the **ratio** effect instead, compare 0.9 versus 0.7 with PLE placement
held fixed and the same matched workload. Existing ratio-0.9 coding/long-context
runs differ from these screens and cannot establish that speed delta.
