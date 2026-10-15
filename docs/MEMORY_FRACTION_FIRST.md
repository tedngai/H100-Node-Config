# First decision: memory fraction versus six-user capacity

**Policy update:** the operator authorized capacity-first screening and separately
approved c6 cold 100K/512, 200K/512, 230K/512, 250K/512, 250K/4096, 256K/512 and
250K/4096 five-round, synchronized ten-round, and one-second-staggered ten-round
follow-ups on the unchanged 0.88 candidate. Queueing and the former 3 GiB floor are
advisory, not default failures. Historical reports and stop instructions below retain
their original criteria; they are not silently reclassified.

## Latest result — capacity-first repeat PASSED (17:27–17:29 UTC)

The operator explicitly requested rewriting acceptance rules and repeating the
test. On the same unchanged 0.88 candidate, **all three c6 rounds completed**:
18 requests, each exactly **100,000 input / 512 output tokens**, zero cache hits,
zero retractions, no observed OOM, no container restart, and unchanged configuration.
The service was idle after every round and in the final audit. Sampled running
count reached **6**; sampled waiting peaked at **5**. Those are separate peaks, not
eleven simultaneous requests. Queueing is included in timings and is not a capacity
failure under the operator-approved new policy.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 137.04 / 135.19 / 137.42 |
| Median aggregate output tok/s | **137.04** |
| Median TTFT | **11.650 s** |
| Median total request latency | **22.290 s** |
| Per-GPU minimum free MiB | **2,285 / 2,719 / 2,719 / 2,927** |
| Scheduler / GPU samples | 351 / 75 |

Starting free memory was 2,297 / 2,731 / 2,731 / 2,939 MiB; the new observed minima
are only 12 MiB lower per device. This run did not repeat the earlier large memory
drop, but that does not identify its cause or prove larger workloads are safe.
The low-memory warning remains visible. p95 is unavailable with only 18 samples.

Final traffic matched exactly **18 POST /generate**, 7 info GETs, 7 model GETs and
356 load GETs, with no logged OOM/error markers or unparsed request lines. An initial
final-audit worksheet expected one extra load GET; that arithmetic-only audit is
retained, followed by an offline correction. No retry inference was needed.

Evidence: [pretest inventory](../evidence/memory-088-c6-100k-capacity-pretest-20261015T172646.504097Z.json),
[preflight](../evidence/memory-088-c6-100k-capacity-preflight-20261015T172701.563189Z.json),
[capacity benchmark](../evidence/memory-088-c6-100k-capacity-20261015T172705.631735Z.json),
[posttest inventory](../evidence/memory-088-c6-100k-capacity-posttest-20261015T172840.358925Z.json),
[initial audit arithmetic error](../evidence/memory-088-c6-100k-capacity-final-audit-20261015T172903.600881Z.json),
[corrected final audit](../evidence/memory-088-c6-100k-capacity-final-audit-corrected-20261015T172913.001170Z.json).

**Disposition:** leave 0.88 running, original baseline preserved/stopped. This was a
successful bounded 100K capacity screen, not sustained six-user or universal
OOM-safety qualification. The separately approved 200K stage is recorded next;
historical strict failures below remain unchanged.

## Capacity-first c6 200K PASSED (17:34–17:38 UTC)

After a new idle-window preflight, the operator approved one c6 cold 200K/512,
three-round screen. Candidate identity, argv/image, effective configuration, model
metadata and GPU identity matched the same 0.88 startup. Baseline integrity was
preserved, the original container remained stopped, and recent traffic was exactly
the expected read-only preflight GETs. Six 200K inputs plus outputs reserved
**1,203,072 / 1,717,184 slots (70.1%)**, below the 90% pool guard.

All **18/18 requests completed** with exactly 200,000 input and 512 output tokens,
zero cache hits and zero retractions. Sampled running reached **6**, waiting peaked
at **5** (459 of 680 load samples reported waiting); queueing is informational in
this policy and is included in client TTFT/latency. No OOM marker, request error,
container restart, error log marker, configuration drift or unrelated inference was
observed. The service was idle after each round and at final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 62.72 / 62.69 / 62.73 |
| Median aggregate output tok/s | **62.72** |
| Median TTFT | **27.234 s** |
| Median total request latency | **48.871 s** |
| Per-GPU minimum free MiB | **2,265 / 2,697 / 2,699 / 2,905** |
| Scheduler / GPU samples | 680 / 140 |

The minimum free memory was 20–22 MiB below pretest readings and remained at those
levels after the service returned idle. The 3 GiB warning therefore remains; no hard
floor was configured. Eighteen samples are insufficient for p95.

Evidence: [inventory](../evidence/memory-088-c6-200k-capacity-pretest-20261015T173438.187532Z.json),
[preflight](../evidence/memory-088-c6-200k-capacity-preflight-20261015T173457.039082Z.json),
[benchmark](../evidence/memory-088-c6-200k-capacity-20261015T173458.878483Z.json),
[posttest inventory](../evidence/memory-088-c6-200k-capacity-posttest-20261015T173758.755641Z.json),
[final audit](../evidence/memory-088-c6-200k-capacity-final-audit-20261015T173835.134422Z.json).

**Disposition at that stage:** c6 200K passed as a bounded capacity screen under
capacity-first-v1. The separately approved 230K stage is recorded next. Candidate
remained running/idle; baseline remained preserved/stopped.

## Next approved stage — capacity-first c6 230K PASSED (17:41–17:45 UTC)

The operator approved the next staged workload: six cold 230,000-input / 512-output
requests, three rounds, same 0.88 profile and unchanged settings. Fresh preflight
passed: candidate was ready/idle with matching identity, model and GPU health; no
new inference/OOM traffic since the prior audit; baseline intact. Budget was
**1,383,072 / 1,717,184 slots (80.5%)**, below the 90% pool guard.

All **18/18 requests completed** with exact token accounting, zero cache hits and
zero retractions. No OOM, runtime error, restart, configuration drift or unrelated
inference was observed. Sampled running reached **6**; waiting peaked at **5** in
566/811 load samples and remains an informational queue observation. The service
was idle after each round and at final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 51.70 / 51.90 / 51.77 |
| Median aggregate output tok/s | **51.77** |
| Median TTFT | **33.340 s** |
| Median total request latency | **59.162 s** |
| Per-GPU minimum free MiB | **2,263 / 2,695 / 2,695 / 2,903** |
| Scheduler / GPU samples | 811 / 167 |

Free memory remained near the pretest values (2,265 / 2,697 / 2,699 / 2,905 MiB);
the 3 GiB advisory warning persists. This 18-request screen has no p95 and does not
establish universal OOM safety or sustained production performance.

Evidence: [pretest inventory](../evidence/memory-088-c6-230k-capacity-pretest-20261015T174158.843807Z.json),
[preflight](../evidence/memory-088-c6-230k-capacity-preflight-20261015T174209.554952Z.json),
[benchmark](../evidence/memory-088-c6-230k-capacity-20261015T174211.686782Z.json),
[posttest inventory](../evidence/memory-088-c6-230k-capacity-posttest-20261015T174534.443400Z.json),
[final audit](../evidence/memory-088-c6-230k-capacity-final-audit-20261015T174546.906513Z.json).

**Disposition at that stage:** 230K passed as a bounded capacity-first screen. The
separately approved 250K stage is recorded next. Candidate remained running/idle;
original baseline remained stopped and preserved.

## Current target stage — capacity-first c6 250K PASSED (17:49–17:53 UTC)

The operator separately approved six cold 250,000-input / 512-output requests for
three rounds. Fresh preflight passed with the same ready/idle 0.88 candidate, exact
identity/config/model/GPU checks, no intervening inference, and intact baseline.
The workload reserved **1,503,072 / 1,717,184 slots (87.53%)**, within the 90%
guard by **42,393 slots**; each prompt plus output fits the 262,144-token context.

All **18/18 requests completed** with exact token counts, zero cache hits, and zero
retractions. No observed OOM, request/log error, restart, configuration drift, or
unrelated inference. Sampled running reached **6**; waiting peaked at **5** in
638/907 load samples. Queueing remains informational and included in timings. The
server was idle after every round and at final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 45.96 / 46.03 / 46.04 |
| Median aggregate output tok/s | **46.03** |
| Median TTFT | **37.612 s** |
| Median total request latency | **66.641 s** |
| Per-GPU minimum free MiB | **1,629 / 2,063 / 2,063 / 2,271** |
| Scheduler / GPU samples | 907 / 187 |

Memory is the key caution: pretest free memory was 2,263 / 2,695 / 2,695 / 2,903
MiB, and sampled minima fell by **634 MiB on each GPU**, remaining at the lower
values after idle. No OOM occurred, but this warns against extrapolating to longer
outputs, sustained traffic, or 256K prompts. Eighteen requests do not provide p95
or universal OOM-safety evidence.

Evidence: [pretest inventory](../evidence/memory-088-c6-250k-capacity-pretest-20261015T174905.919279Z.json),
[preflight](../evidence/memory-088-c6-250k-capacity-preflight-20261015T174917.430990Z.json),
[benchmark](../evidence/memory-088-c6-250k-capacity-20261015T174919.391119Z.json),
[posttest inventory](../evidence/memory-088-c6-250k-capacity-posttest-20261015T175305.295411Z.json),
[final audit](../evidence/memory-088-c6-250k-capacity-final-audit-20261015T175314.561930Z.json).

**Disposition:** the stated 250K-input six-user capacity screen passed under
capacity-first-v1. Candidate remains running and idle; original baseline remains
stopped and preserved. 256K, 0.90, DP2 and HiCache were not tested or authorized.

## Longer-output follow-up — capacity-first c6 250K/4096 PASSED (18:04–18:09 UTC)

The operator approved one-factor follow-up: same six cold 250,000-input prompts and
0.88 configuration, increasing forced output from 512 to **4,096 tokens**, three
rounds. Preflight verified the same ready/idle candidate and baseline integrity,
with no new inference between audits. The budget was **1,524,576 / 1,717,184 slots
(88.78%)**, 20,889 slots under the 90% guard; 254,096 tokens per request fits the
262,144 context.

All **18/18 requests completed** exactly, with zero cache hits/retractions and no
observed OOM, request/log error, restart, drift or unrelated inference. Sampled
running reached **6**, waiting peaked at **5** (639/1,154 load samples). The service
was idle after each round and in the final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 281.58 / 283.34 / 280.90 |
| Median aggregate output tok/s | **281.58** |
| Median TTFT | **37.647 s** |
| Median total request latency | **86.579 s** |
| Per-GPU minimum free MiB | **1,629 / 2,063 / 2,063 / 2,271** |
| Scheduler / GPU samples | 1,154 / 237 |

The sampled memory minimum was unchanged from the 250K/512 screen; the low-memory
warning remains. No p95 is reported for 18 requests. This is a bounded screen, not
universal OOM-safety or production qualification.

Evidence: [pretest inventory](../evidence/memory-088-c6-250k-4k-capacity-pretest-20261015T180413.074787Z.json),
[preflight](../evidence/memory-088-c6-250k-4k-capacity-preflight-20261015T180424.039433Z.json),
[benchmark](../evidence/memory-088-c6-250k-4k-capacity-20261015T180446.714846Z.json),
[posttest inventory](../evidence/memory-088-c6-250k-4k-capacity-posttest-20261015T180935.566478Z.json),
[final audit](../evidence/memory-088-c6-250k-4k-capacity-final-audit-20261015T180948.379876Z.json).

**Disposition at that stage:** candidate remained running and idle; original baseline
remained stopped/preserved. The separately approved 256K/512 stage is recorded next.

## Near-guard stage — capacity-first c6 256K/512 PASSED (18:17–18:21 UTC)

The operator approved six cold 256,000-input / 512-output requests for three rounds
on unchanged memory-088. Fresh preflight passed identity, configuration, model/GPU,
idle, traffic and baseline-integrity checks. Requested occupancy was **1,539,072 /
1,717,184 slots (89.63%)**, just **6,393 slots** below the 90% guard. Each request
fits the 262,144-token context.

All **18/18 requests completed** with exact token counts, zero cache hits, and zero
retractions. No observed OOM, request/log error, restart, configuration drift, or
unrelated inference. Sampled running reached **6**; waiting peaked at **5** in
662/932 load samples. The service returned idle after every round and at final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 44.44 / 44.59 / 44.57 |
| Median aggregate output tok/s | **44.57** |
| Median TTFT | **38.786 s** |
| Median total request latency | **68.856 s** |
| Per-GPU minimum free MiB | **1,629 / 2,063 / 2,063 / 2,271** |
| Scheduler / GPU samples | 932 / 190 |

The memory minimum was unchanged from the 250K stages. The low-memory warning
persists; the narrow token-pool margin is the key limitation. Eighteen requests do
not provide p95 or universal OOM-safety evidence.

Evidence: [pretest inventory](../evidence/memory-088-c6-256k-capacity-pretest-20261015T181716.810735Z.json),
[preflight](../evidence/memory-088-c6-256k-capacity-preflight-20261015T181730.120464Z.json),
[benchmark](../evidence/memory-088-c6-256k-capacity-20261015T181734.050944Z.json),
[posttest inventory](../evidence/memory-088-c6-256k-capacity-posttest-20261015T182126.588858Z.json),
[final audit](../evidence/memory-088-c6-256k-capacity-final-audit-20261015T182137.670129Z.json).

**Current disposition:** 256K/512 passed as a bounded capacity-first screen, not
universal OOM-safety or production qualification. Candidate remains running/idle;
original baseline remains stopped/preserved. Larger output at this input, 0.90,
DP2 and HiCache were not tested or authorized.

## Five-round repeat — c6 cold 250K/4096 PASSED (18:31–18:39 UTC)

To obtain an initial p95 view and check repeatability, the operator approved five
rounds at the unchanged 250,000-input / 4,096-output workload (30 requests total).
Fresh preflight again verified the same ready/idle candidate, no intervening
inference, and a passing 90% pool budget of **1,524,576 / 1,717,184 slots (88.78%)**.

All **30/30 requests completed** with exact token counts, zero cache hits and zero
retractions. No OOM/runtime error, restart, drift or unrelated inference was
observed. Sampled running reached **6**, waiting peaked at **5** (1,064/1,915 load
samples); the service was idle after each round and at the final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 282.25 / 282.40 / 282.50 / 283.00 / 283.70 |
| Median aggregate output tok/s | **282.50** |
| Median TTFT / initial p95 | **37.630 s / 63.782 s** |
| Median latency / initial p95 | **86.547 s / 86.956 s** |
| Per-GPU minimum free MiB | **1,629 / 2,063 / 2,063 / 2,271** |
| Scheduler / GPU samples | 1,915 / 390 |

The 30-request p95 is only an initial, weak tail estimate. Free memory and the low-
memory warning were unchanged from the prior screen. No OOM was observed; this does
not prove universal OOM safety or production behavior.

Evidence: [pretest inventory](../evidence/memory-088-c6-250k-4k-5round-capacity-pretest-20261015T183051.868316Z.json),
[preflight](../evidence/memory-088-c6-250k-4k-5round-capacity-preflight-20261015T183118.637110Z.json),
[benchmark](../evidence/memory-088-c6-250k-4k-5round-capacity-20261015T183122.659160Z.json),
[posttest inventory](../evidence/memory-088-c6-250k-4k-5round-capacity-posttest-20261015T183917.920359Z.json),
[final audit](../evidence/memory-088-c6-250k-4k-5round-capacity-final-audit-20261015T183931.332380Z.json).

**Current disposition:** the approved 250K/4096 five-round screen passed. Candidate
remains running and idle; original baseline remains stopped/preserved. No additional
workload or configuration change is authorized by this result.

## Ten-round repeat — c6 cold 250K/4096 PASSED (19:18–19:34 UTC)

The operator approved ten rounds of the same six-user, cold 250,000-input /
4,096-output workload (60 requests). Fresh preflight confirmed the unchanged ready,
idle 0.88 candidate, clean traffic window and intact baseline. The reservation stayed
at **1,524,576 / 1,717,184 slots (88.78%)**, leaving **20,889 slots** under the 90%
guard.

All **60/60 requests completed** with exact token counts, zero cache hits and zero
retractions. No observed OOM, request/log error, restart, configuration drift or
unrelated inference. Sampled running reached **6**; waiting peaked at **5** (2,129
of 3,884 load snapshots). The service was idle after each round and at final audit.

| Measure | Result |
|---|---:|
| Per-round aggregate output tok/s | 282.61 / 283.58 / 282.73 / 283.93 / 277.47 / 269.47 / 282.66 / 282.59 / 274.65 / 276.89 |
| Median aggregate output tok/s | **282.60** |
| Median TTFT / initial p95 | **37.656 s / 63.769 s** |
| Median latency / initial p95 | **86.438 s / 88.551 s** |
| Per-GPU minimum free MiB | **1,629 / 2,063 / 2,063 / 2,271** |
| Scheduler / GPU samples | 3,884 / 788 |

This extends the initial p95 view from 30 to 60 requests, but it is still limited
tail evidence. Queueing and low free memory remain warnings; the minimum sampled
free memory is below 3 GiB. No OOM was observed, which does not prove universal OOM
safety or production behavior.

Evidence: [pretest inventory](../evidence/memory-088-c6-250k-4k-10round-capacity-pretest-20261015T191737.497419Z.json),
[preflight](../evidence/memory-088-c6-250k-4k-10round-capacity-preflight-20261015T191815.998355Z.json),
[benchmark](../evidence/memory-088-c6-250k-4k-10round-capacity-20261015T191820.944284Z.json),
[posttest inventory](../evidence/memory-088-c6-250k-4k-10round-capacity-posttest-20261015T193421.003209Z.json),
[final audit](../evidence/memory-088-c6-250k-4k-10round-capacity-final-audit-20261015T193456.102156Z.json).

**Current disposition:** this approved ten-round screen passed. Candidate remains
running and idle; original baseline remains stopped/preserved. No additional
workload or configuration change is authorized by this result.

## Staggered-arrival comparison — c6 cold 250K/4096 PASSED (19:43–20:00 UTC)

The operator approved a matched arrival-pattern comparison: ten rounds, six cold
250,000-input / 4,096-output requests per round, with client starts staggered at
**0, 1, 2, 3, 4 and 5 seconds**. The model, 0.88 configuration, cache state and
request sizes stayed fixed. Fresh preflight passed. Pool occupancy remained
**1,524,576 / 1,717,184 slots (88.78%)**, leaving **20,889 slots** under the guard.

All **60/60 requests completed** with exact token counts, zero cache hits and zero
retractions. No observed OOM, request/log error, restart, configuration drift or
unrelated inference. Every measured client-start offset matched its scheduled offset
within **0.4 ms**. Sampled running reached **6**, waiting peaked at **5** (2,093 of
3,839 load snapshots), and the server returned idle after every round and at final
audit.

| Measure | Synchronized starts | 1-second stagger |
|---|---:|---:|
| Median aggregate output tok/s | 282.60 | **283.45** |
| Median TTFT / initial p95 | 37.656 / 63.769 s | **35.019 / 58.604 s** |
| Median latency / initial p95 | 86.438 / 88.551 s | **83.829 / 86.211 s** |
| Peak sampled waiting / running | 5 / 6 | 5 / 6 |
| Per-GPU minimum free MiB | 1,629 / 2,063 / 2,063 / 2,271 | unchanged |

These are separate 60-request screens, not a paired experiment; the lower latency
observed here does not establish a causal or statistically stable benefit. Both p95s
are limited estimates. Low free memory remains a warning; no universal OOM-safety or
production claim follows.

Evidence: [pretest inventory](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-pretest-20261015T194338.832606Z.json),
[preflight](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-preflight-20261015T194352.975513Z.json),
[benchmark](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-20261015T194356.729711Z.json),
[posttest inventory](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-posttest-20261015T195955.117967Z.json),
[final audit](../evidence/memory-088-c6-250k-4k-stagger1-10round-capacity-final-audit-20261015T200033.663353Z.json).

**Current disposition:** this approved staggered screen passed. Candidate remains
running and idle; original baseline remains stopped/preserved. No further workload
or configuration change is authorized.

## Live result — 2026-10-15, 16:32 UTC

The operator explicitly authorized the switch and initial bounded testing.
**`sglang-qwen38-flash-next-088` is now running** at the existing endpoint. The
original container was stopped cleanly and is preserved for restoration. No image
was pulled or committed; environment values were copied only in memory over the
local Docker socket and were not printed or saved. Image/runtime settings and
argv were preserved except the intended fraction change. Source-file checks found
no changed `.py` runtime files under the source/package paths checked.

Measured startup capacity is **1,717,184 tokens**, up **129,216 (+8.1%)** from
1,587,968, above the illustrative earlier estimate. The 90% guard is about
**1,545,466 slots**. Six 250K inputs + 512 outputs fit arithmetically, but have
not been tested. Six 256K inputs + 512 outputs fit by only about 6,394 guarded
slots, so this is not sufficient evidence of safe near-full-context admission.
The per-request context remains 262,144; effective active cap remains 48. Hybrid
state slots increased from 611 to 656; target KV reports 20.881 GiB versus 19.310.

All three smoke cases passed. The initial cold c1 screen completed three exact
32,768-input / 512-output requests, with zero sampled waiting/retractions. Median
aggregate throughput was 179.75 tok/s, TTFT 0.996 s, and latency 2.847 s. The first
round was slower (105.65 tok/s), so this startup screen is not a controlled speed
comparison. Sampled minimum free memory by GPU was **3,967 / 4,401 / 4,401 / 4,609
MiB**. A conservative 2,048 MiB sampled-free floor was used to review this initial
c1 stage only; it is not a measured workspace requirement or six-user safety limit.

Both post-audits passed with exact expected inference traffic, idle loads and
unchanged candidate identity/configuration/model metadata. No error/warning markers
were detected in the final decode audit. Samples can miss peaks: **six-user
long-context and OOM safety remain unqualified**. Candidate is left running for
testing; no 0.90 change was made.

Evidence: [switch](../evidence/memory-088-container-switch-20261015T162632.591826Z.json),
[startup](../evidence/memory-088-startup-20261015T163116.728290Z.json),
[initial gates](../evidence/memory-088-initial-test-gates-20261015T163122.322262Z.json),
[smoke](../evidence/memory-088-smoke-20261015T163124.088083Z.json),
[smoke audit](../evidence/memory-088-smoke-post-audit-20261015T163146.391110Z.json),
[decode](../evidence/memory-088-c1-32k-cold-decode-20261015T163148.760048Z.json),
[post-inventory](../evidence/memory-088-post-initial-test-20261015T163219.266050Z.json),
[final audit](../evidence/memory-088-initial-decode-post-audit-20261015T163238.573368Z.json).

## Six-user 100K cold screen — strict failure, stop here (16:44 UTC)

Following a corrected passing preflight, one c6 round submitted six cold
100,000-input / 512-output decode requests. All six completed exactly 512 tokens
with zero retractions. However, the strict benchmark observed queueing (peak sampled
waiting **5**) and correctly stopped before rounds two and three. This is a **failed
strict no-queue screen**, not a pass. Median aggregate throughput for the one
completed round was **129.48 tok/s**, median TTFT **11.874 s**, and median latency
**23.461 s**; these six requests do not provide p95.

The per-GPU 3,072 MiB stop floor was also crossed. One-second samples reached only
**2,297 / 2,731 / 2,731 / 2,939 MiB free**. This is not evidence of OOM (none was
reported), but it is below the pre-agreed operating floor. Loads were idle after
the requests; candidate remained ready, and the baseline container remains
preserved/stopped. **Do not continue c6/longer tests on this candidate under the
current protocol.** No retry or later round was run. The earlier failed preflight
that compared against the pre-reboot host GPU query is retained; a corrected check
against the post-reboot candidate-start inventory passed before inference.

Evidence: [initial preflight mismatch](../evidence/memory-088-c6-100k-preflight-20261015T164329.377203Z.json),
[corrected preflight](../evidence/memory-088-c6-100k-preflight-recheck-20261015T164401.788439Z.json),
[benchmark failure](../evidence/memory-088-c6-100k-cold-decode-20261015T164404.677968Z.json),
[posttest inventory](../evidence/memory-088-c6-100k-posttest-20261015T164440.834890Z.json),
and [traffic/memory audit](../evidence/memory-088-c6-100k-post-traffic-audit-20261015T164527.380571Z.json).

The benchmark now summarizes sampled memory and records a floor breach even when
another validation error (such as queueing) ends a run early. Offline tests were
rerun after this harness change. This code correction does not authorize a retry.

## Original offline analysis and planning (historical)

Planning/read-only analysis, 2026-10-15. No setting, startup, allocation stress
test, or inference was performed. This is the first decision gate before DP2,
HiCache, or a broader tuning matrix.

## Preliminary answer

| Static fraction | Shared token slots | 90% guarded budget | Added static budget / GPU |
|---|---:|---:|---:|
| 0.85 | **1,587,968 observed** | 1.429M | Baseline |
| 0.88 | Approximately 1.68–1.69M estimated | 1.515–1.522M estimated | About 2.39 GiB |
| 0.90 | Approximately 1.75–1.76M estimated | 1.572–1.584M estimated | About 3.98 GiB |

Estimate ranges are illustrative accounting scenarios, **not confidence bounds**
or measured candidate capacities. Automatic allocation changes could move the
actual result outside them. Per-request context remains 262,144 including output.

Six 250K inputs + 512 output each need 1,503,072 slots, or at least 1,670,080
reported slots under the 90% guard. Six 256K inputs + 512 output each need
1,539,072 slots, or at least 1,710,080 reported slots. Thus **0.88 might already
meet the six-250K target**, while 0.90 might cover six-256K. Neither is qualified;
the small projected surplus at 0.88 warrants caution, especially for longer output.

## How the estimate was made

Read-only inspection of the container source found:

- `mem_cache/kv_cache_configurator.py::_profile_available_bytes`: subtracts
  `pre_model_load_memory * (1 - mem_fraction_static)` as runtime slack before
  deriving the pool budget. It uses pre-load available memory, not a fixed fraction
  of today's NVML-free memory.
- `_handle_max_mamba_cache`: automatic hybrid allocation uses
  `mamba_full_memory_ratio / (1 + mamba_full_memory_ratio)` for hybrid state;
  at the current ratio 0.9, the approximate full-attention remainder is 52.63%.
  Speculative intermediate state and discrete request/state caps complicate this.
- `model_executor/pool_configurator.py`: computes token capacity from bytes per
  token, accounts for draft layers, and page-aligns it.
- Reported `memory_usage.kvcache` is the target KV pool, not a complete memory
  ledger. Draft, hybrid state, graphs, activations, and other allocations matter.

Approximate a five-percentage-point increase as 0.05 × 79.647 GiB ≈ 3.982 GiB
per GPU, with about 2.096 GiB going to the full-attention budget. Extrapolate from
the observed 1,587,968 tokens / 19.31 GiB target KV allocation, illustrating
uncertainty from draft-KV accounting (one draft layer versus twelve full-attention
layers). The result is roughly 159K–172K additional shared slots, not a fourfold
sum of the per-GPU gain and not simply 1,587,968 × 0.90/0.85.

Exact pre-model-load free memory and a complete loaded-process allocation ledger
are not captured. Source is in an editable install; present source inspection is
not proof of every function already imported by the running process. Cache model
metadata likewise is not proof of loaded weights. Treat this as a feasibility
estimate pending a controlled, identity-checked candidate startup.

Evidence and source hashes:
[`memory-fraction-offline-estimate-20261015T150548.923661Z.json`](../evidence/memory-fraction-offline-estimate-20261015T150548.923661Z.json).
The historical inventory is timestamped 14:40 UTC; no fresh idle claim is made.

## OOM risk: what can and cannot be answered offline

Increasing the fraction reallocates runtime slack to persistent pools. It does
not create memory. Startup success alone cannot establish safety during long
prefill, speculative verification, six-user mixed decode, or cache churn.

The historical inventory showed a minimum NVML-free value of about 6.19 GiB per
GPU. Subtracting only the estimated additional allocations would leave about
3.80 GiB at 0.88 or 2.21 GiB at 0.90. These are **illustrative historical
extrapolations**, not predicted live free memory or proof of usable CUDA workspace.
Allocator reservations, graph pools, transient peaks, and automatic setting
changes make simple free-memory subtraction insufficient to assess OOM safety.

There is no defensible offline OOM probability or unconditional safe/unsafe verdict.
Known required workspace larger than the available margin can reject a candidate;
otherwise, bounded live qualification can reduce uncertainty but cannot prove
absence of OOM for every workload.

## Revised next experiment, requiring separate approval

1. Write a memory-only candidate protocol and reviewed stop/restore procedure.
   Keep TP4/EP4/DP1, speculation, chunk size, admission flags, image and model fixed;
   record automatic effective changes. Preserve the original container/baseline.
2. In an explicitly approved maintenance/idle window, test **0.88 first** and
   capture actual per-rank token/state capacity, graph allocations and readiness.
   Do not run a second full model beside the baseline.
3. After startup gates, run bounded smoke and staged load checks: short c1,
   concurrent 32K, then c2/c4/c6 at 100K and 200K with guarded budgets. Measure
   prefill/decode peaks and sample device/process allocator data where supported;
   missing peak telemetry remains unavailable, not proof of margin.
4. Test six 230K, then six 250K only if lower stages and actual capacity pass.
   Include long prefill while other users decode, warm-history churn, and explicitly
   budgeted longer output. Define queue/stall limits and memory abort margins before
   execution; do not deliberately drive the service to OOM to find the limit.
5. If 0.88 meets the requirement and has adequate measured margin, prefer it over
   0.90. Consider 0.90 only after 0.88 passes, measurements support sufficient
   headroom, and the remaining capacity need justifies it. It needs separate approval.
6. Stop after startup failure, unhealthy memory state, out-of-policy queueing,
   error/retraction/correctness failure, interference or drift. Preserve partial
   evidence; no automatic retry or further fraction increase. Returning to baseline
   must follow the approved restoration procedure and readiness checks.

Long-context scheduling still needs a reviewed protocol before six-user live stages.
The new one-second sampler is not a transient-peak/OOM safety monitor. Do not
reinterpret the strict no-queue benchmark or the existing fixed-32K scheduled test
as an already implemented long-context protocol. Run the required offline unit tests
after any harness changes.

## Prepared 0.88 profile and candidate-only memory sampling

The existing `memory-088` candidate now explicitly tolerates SGLang's **automatic
`max_running_requests` change** while still requiring every other non-allocation
setting to match the baseline. Token capacity and Mamba state capacity are recorded
from the candidate; they are not asserted in advance. It remains a one-factor
change: only `--mem-fraction-static 0.88` is added/replaced.

`tests/benchmark.py --profile memory-088` now requires working `/v1/loads` scheduler
telemetry and a pre-inference host `nvidia-smi` query. During the benchmark it samples
per-GPU total/used/free memory about once per second, and again after the run. It
stores sanitized numeric samples only—no raw command output, UUID, or environment.
Telemetry failure fails the report. It records minimum free and maximum used MiB
per device; it never sums TP devices.

The sampler does not prove OOM safety or cancel live requests. One-second polling can
miss transient peaks; aggregate GPU use is not process attribution and idle/post-run
free memory is not a peak-workspace measurement. The 0.88 benchmark requires a
per-GPU free-memory floor and checks it before inference, at each round boundary, and
afterward. A breach preserves that round and prevents later rounds, but cannot cancel
the current round's already submitted requests.

### Offline inspection (safe; sends no requests)

```bash
python3 -B -m unittest discover -s tests -v
python3 -B tests/profiles.py memory-088
python3 -B tests/profiles.py memory-088 --shell
```

The printed SGLang command is candidate argv only, **not a Docker launch command**.
No deployment helper is provided: preserve the current container and use a separately
approved, reviewed maintenance/restore procedure. Never run the candidate alongside
the baseline model on these GPUs.

### Conditional live sequence — not authorized by this document

Only after separate explicit approval, a coordinated idle/maintenance window, a
reviewed rollback procedure, and an agreed memory stop margin:

1. Manually start the candidate from the pinned baseline image and preserved runtime
   settings, with a distinct container name (example below). The baseline container
   must be safely preserved and stopped first; this plan does not authorize that
   operation.
2. Capture candidate startup inventory (read-only):

   ```bash
   python3 -B tests/capture_baseline.py --label memory-088-startup \
     --container sglang-qwen38-flash-next-088
   ```

   Inspect the timestamped report: ready status, exact image ID, exact argv from
   `profiles.py`, `mem_fraction_static: 0.88`, TP4/EP4/DP1, actual shared token and
   Mamba capacities, effective active cap, GPU health/free memory, and unchanged
   model metadata. Stop if anything besides expected allocation/admission results
   changed. Capture itself sends no inference.
3. After a fresh traffic/idle check, run smoke once:

   ```bash
   python3 -B tests/smoke_test.py --label memory-088-smoke \
     --profile memory-088 --execute --confirm-idle
   ```

4. If smoke and audit pass, first run a bounded c1 sample to exercise the candidate
   sampler:

   ```bash
   python3 -B tests/benchmark.py --label memory-088-c1-32k-cold-decode \
     --profile memory-088 --container sglang-qwen38-flash-next-088 \
     --mode decode --cache cold --concurrency 1 --prompt-tokens 32768 \
     --output-tokens 512 --rounds 3 --min-free-gpu-mib 2048 \
     --execute --confirm-idle
   ```

   Review GPU-memory samples, correctness, queue/retraction telemetry, the post-run
   idle state, traffic, and inventory before the next separate invocation.
5. Only after the c1 gate, use separately approved c6 stages (100K, 200K, then
   230K; 250K only if measured capacity and pre-agreed headroom support it). For
   example, the **first c6 100K screen**, not a full matrix, is:

   ```bash
   python3 -B tests/benchmark.py --label memory-088-c6-100k-cold-decode \
     --profile memory-088 --container sglang-qwen38-flash-next-088 \
     --mode decode --cache cold --concurrency 6 --prompt-tokens 100000 \
     --output-tokens 512 --rounds 3 --min-free-gpu-mib 3072 \
     --execute --confirm-idle
   ```

   The strict benchmark stops on any sampled waiting. Preserve a failure; do not
   retry or silently treat it as a pass. Do not advance to warm-cache, mixed
   staggered traffic, or near-limit cases until a reviewed long-context protocol
   defines those cases and their queue/stall/memory abort criteria. Existing scheduled
   screening is fixed at 32K and is not a substitute.

Each command is a distinct live invocation and needs the required approval. The
`--execute --confirm-idle` flags are mandatory assertions, not approval or proof
that other clients are absent. Audit traffic and fresh idle loads after every run.
The 3,072 MiB c6 threshold preserves the free-memory margin observed in the previous
c1 screen, but is only an operational stop trigger, not a CUDA workspace requirement
or OOM guarantee. At a breach the harness stops before another round; it cannot
cancel requests already in flight. Sampling cannot guarantee OOM prevention.
