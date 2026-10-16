# PLE offload comparison — baseline and proposed protocol

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

## Critical prerequisite: verify current PLE placement

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
