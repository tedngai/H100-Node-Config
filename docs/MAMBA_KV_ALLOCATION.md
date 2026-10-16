# Offline Mamba / KV allocation investigation

**Live update — 2026-10-16, 02:14 UTC:** following separate operator deployment and
maintenance-window approval, MTP-on ratio **0.7** is now serving. Startup and all three
interface smoke checks passed. Measured shared capacity is **1,806,656 tokens**
(+5.21% versus ratio 0.9), state slots **570**, effective admission **48**. Context
remains 262,144. The ratio-0.9 container is stopped/preserved for rollback. No cache
flush or benchmark was run; long-context performance and state-retention behavior
remain unqualified. See the deployment evidence below.

The analysis below was originally performed offline, before that deployment. Its
estimates are retained separately from the measured startup result.

## What explains the MTP-off capacity loss?

The ratio is a **nominal Mamba-state/full-KV budget ratio**, not a percentage of
VRAM. At `r=0.9`, the initial Mamba budget is `B * r / (1+r)`, or about 47.4% of
the available cache-sizing budget `B`. The actual split can differ because the
speculative sizing and allocation formulas use different request bounds.

The inspected SGLang source does the following:

1. Profiles free memory and subtracts runtime slack/reservations.
2. Solves for persistent Mamba state slots `K` from that nominal Mamba budget.
3. With MTP, budgets speculative intermediate states using `K / q`, but actually
   subtracts scratch for `min(configured_request_cap, K // q)` requests.
4. Subtracts persistent Mamba states and gives the remaining budget to KV sizing.
   KV sizing also charges for the MTP draft attention layer.

For the default overlap extra-buffer path, `q=5` state slots per request. The
observed off-arm limit is consistent with this: `1226 // 5 = 245`. With four draft
tokens (`D=4`), per-slot state cost `S`, and nominal Mamba budget `M`, the source's
non-ReplaySSM branch solves:

```text
M = B * r / (1 + r)
MTP on:  K = floor((M - S*(1+D)) / (S*(1+D/q)))
         scratch = S * (min(48, K//q) + 1) * D
MTP off: K = floor((M - S) / S), scratch = 0
KV sizing budget = B - (K+1)*S - scratch
```

The `+1` terms account for padding slots. MTP-on's `K=656` would support a
state-derived bound of 131 under this model, but its configured cap is **48**.
Scratch is therefore sized for 49 padded request slots, not roughly 132. The
unused nominal reserve becomes available to KV. MTP-off does not have that scratch
reservation/cap interaction: it fills the nominal state budget with **1,226
persistent slots** instead.

Thus **removing MTP does not preserve a fixed Mamba allocation and simply donate
the freed scratch to KV**. The allocator recomputes the split. This is an allocation
policy effect, not evidence that MTP inherently saves memory in all configurations.

## Numerical consistency check

The selected cached model dimensions and inspected source give 36 linear-attention
layers, 12 full-attention layers, and **14,708,736 bytes (14.027 MiB) per Mamba slot
per TP rank**, assuming the recorded BF16 state types and TP4/PP1 layout.

| Component, per rank | MTP-on | MTP-off |
|---|---:|---:|
| Observed persistent state slots | 656 | 1,226 |
| Modeled persistent state memory, including padding | 9.000 GiB | 16.808 GiB |
| Modeled speculative intermediate reserve | 2.685 GiB | 0 |
| Recorded target-worker KV memory | 20.881 GiB | 18.680 GiB |
| Observed shared token capacity | 1,717,184 | 1,536,000 |

Off-arm modeled persistent-plus-intermediate state memory is about **5.12 GiB
larger**, despite removing speculative scratch. The target KV/QSA cost is 13,056
bytes/token/rank. MTP sizing additionally charges one draft attention layer, giving
14,144 bytes/token/rank. The target-worker `memory_usage.kvcache` number is therefore
not the whole target-plus-draft KV sizing budget. Do not sum duplicate TP metrics.

Back-calibrating `B` from the observed tokens and these formulas reproduces both
reported state-slot counts. That is a **consistency check, not an independent
measurement of every startup allocation**. Different startup budgets, allocator
padding, non-KV buffers, and rounded telemetry prevent an exact free-VRAM audit
from these reports. The inspected source is fingerprinted now; historical hashes
of all these files are unavailable. Cached model metadata matches the recorded
config fingerprint, but does not prove which weights a running process loaded.
The non-ReplaySSM/default-buffer assumptions are explicit in the evidence.

## Selected candidate: MTP-on, ratio 0.7

`memory-088-mamba-070` in `configs/candidates.json` is derived from the immutable
original baseline. Relative to `memory-088`, it changes **only**:

```text
--mamba-full-memory-ratio 0.7
```

It retains static memory fraction 0.88, MTP/NEXTN settings, TP4/EP4/DP1, context,
dtype, and other launch settings. Automatic effective settings must be recaptured.
Offline resolution only:

```sh
python3 -B tests/profiles.py memory-088-mamba-070
```

Holding the reconstructed on-arm sizing budget constant gives these **unmeasured
estimates**, page-aligned to 64 tokens:

| Ratio | Modeled state slots | Estimated shared tokens | Estimated gain |
|---|---:|---:|---:|
| 0.9 reference | 656 | 1,717,184 | — |
| **0.7 initial estimate** | **570** | **1,806,592** | **5.2%** |
| 0.5 sensitivity only | 460 | 1,920,960 | 11.9% |

0.7 is a conservative first step: fewer state slots, while the modeled state-derived
bound remains above the configured 48-request cap. This is **not a measurement of
active concurrency**, a guarantee of six full contexts, or a new per-request context
limit. The latter remains 262,144. Reducing persistent state capacity can reduce
radix/prefix-state retention or increase state pressure; more KV is not automatically
better end-to-end performance. The 0.5 row is not a deployment candidate.

## Deployment and remaining qualification

The operator requested this candidate be pushed live, then explicitly confirmed
paused client traffic and authorized deployment plus the three interface smoke cases.
The existing serving container was cloned into
`sglang-qwen38-flash-next-088-mamba070-20261016t020846`. Checks before stopping the
old service verified the pinned image, ratio-only argv difference, private environment
equality, runtime/mount equivalence, and source fingerprints. Docker's already-reviewed
unset-to-false `OomKillDisable` default normalization was the only host normalization.
The old container remains stopped and unchanged for rollback.

Fresh preflight, serial stop/start, local startup-warmup attribution, exact traffic,
two idle samples, and chat/reasoning/synthetic-tool smoke checks all passed. The tool
smoke does not execute a real tool. Final verification again confirmed ready/idle,
unchanged identity/configuration, preserved stopped containers, and no observed OOM
markers. Only **three harness inference requests** were sent, plus SGLang's built-in
startup warmup. No benchmark or cache flush was performed.

Measured capacity **1,806,656** is one 64-token page above the offline estimate;
state slots **570** match the model. This measures startup pool sizing, **not**
six-user throughput, long-context safety, or warm prefix-state retention. Prior
ratio-0.9 benchmark results do not qualify the new profile. Per operator approval,
the new candidate is left serving, not automatically restored to ratio 0.9.

Any further live benchmark requires separate workload and isolated-window approval.

Before a further live attempt, obtain an approved isolated idle window and agree on
the workload. Capture a fresh MTP-on reference and verify preserved container identities,
exact launch/runtime equivalence, baseline integrity, and traffic. Switch serially
only with explicit approval. Check effective ratio, backend, MTP, pool sizes, direct
per-DP admission cap, readiness, warmup attribution, and two idle samples before
benchmark requests. A reduced state-derived cap is not grounds to silently adjust
the workload or server limits.

Use a matched baseline/candidate workload with identical prompt hashes, output cap,
cache policy, concurrency, and rounds. Record KV/state capacities, sampled GPU memory,
TTFT, completion latency, throughput, queueing, retractions, OOM, and unavailable
metrics. Under capacity-first policy, queueing and low free-memory warnings are
advisory; request accounting, health, and OOM checks remain mandatory. Restore and
verify the agreed serving profile after the test; agree on rollback before any swap
and preserve all probes. The preserved ratio-0.9 container is the deployment rollback
target, not an instruction to undo the successful approved deployment.
No cold-only test establishes warm prefix-state retention quality or universal safety.

## Evidence and source references

- [Approved live deployment and full traffic audit](../evidence/mamba070-live-deployment-20261016T021357.498863Z.json)
- [Three passing interface smoke cases](../evidence/mamba070-live-smoke-20261016T021343.360510Z.json)
- [Postdeployment inventory](../evidence/mamba070-live-postdeploy-20261016T021414.705429Z.json)
- [Final ready/idle/identity verification](../evidence/mamba070-live-final-verification-20261016T021441.350000Z.json)
- [Offline calculations, assumptions, metadata and source SHA-256 fingerprints](../evidence/mamba-kv-allocation-offline-20261016T015951.319611Z.json)
- [MTP-on benchmark](../evidence/coding-mtp-ab-on-64k-2k-20261015T203242.938021Z.json)
- [MTP-off benchmark](../evidence/coding-mtp-ab-off-64k-2k-resume-20261016T010602.359746Z.json)
- Inspected container source root: `/sgl-workspace/sglang/python/sglang/srt/`.
  `mem_cache/kv_cache_configurator.py:1816–1863,1865–1894,1925–1978,2022–2188`
  contains profiling, per-request state ratio, admission, and the state-budget solve.
  `model_executor/pool_configurator.py:149–214,327–383` contains target/draft KV and
  QSA accounting. `configs/mamba_utils.py:110–125,189–237` and
  `configs/qwen3_next.py:288–313` define state dimensions/cost;
  `configs/qwen4_exp.py:15–17,80–87` supplies the inherited configuration/layer map.
  `configs/model_config.py:702–718` gives the single-layer Qwen4 MTP draft;
  `mem_cache/qsa_kv_pool.py:38–53` gives compressed-index bytes/token.
  `server_args.py:2547–2554` defines the ratio's meaning and default.
