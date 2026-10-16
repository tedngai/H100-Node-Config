# Results and experiment history

## 2026-10-14 — setup only

- Captured the existing TP4/EP4 Qwen3.8-Flash-Next-FP8 configuration without changes.
- Preserved active-request cap 48 and 262,144-token context as the baseline.
- Recorded four H100 80GB GPUs and the host NVML/kernel-driver mismatch.
- Prepared review-only candidates, staged workloads, guarded benchmark/interface
  helpers, and an offline unit-test suite.
- No live inference requests, performance tests, cache flushes, deployments,
  service restarts or driver changes were performed during setup.

The baseline inventory is linked by `configs/baseline.json`. Offline validation
and final read-only readiness evidence are recorded separately under `evidence/`.

### Setup validation

Final report: [`setup-validation-20261014T140832.653107Z.json`](../evidence/setup-validation-20261014T140832.653107Z.json).

- **40 offline unit tests passed**, including refusal to run without both live
  confirmation flags, token-budget checks, mocked streaming accounting,
  missing-metric handling, profile isolation, and failed-report preservation.
- Baseline evidence integrity passed; no credential-like strings were detected.
- CPU-only tokenizer check produced two distinct, exactly 1,024-token chat prompts.
- Original container ID, image, argv and start time remained unchanged.
- Read-only server checks still matched the baseline; zero inference requests sent.

Earlier setup-validation reports are retained as development history, not separate
performance measurements.

## 2026-10-14 — preliminary baseline benchmarks

The user approved baseline inference testing. No candidate was applied: image,
launch command, 48-request admission cap, 256K context, and server settings stayed
unchanged. Before testing, the server reported zero active/waiting requests and
there were no generation log entries in the preceding two minutes.

### Short cold-prefix decode screening

Each measured request used **1,024 input tokens and exactly 512 generated tokens**,
with three rounds per concurrency. Prompts requested a sustained technical
explanation rather than only a brief retrieval answer. Rates use client elapsed
time and actual completion counts. All rows below used the same v3 harness.

| Client concurrency | Median aggregate tok/s | Median per-request end-to-end tok/s | Median TTFT | Median request duration | Observed peak active |
|---|---:|---:|---:|---:|---:|
| 2 | 423.25 | 224.96 | 0.433 s | 2.276 s | 2 |
| 4 | 772.06 | 194.44 | 0.451 s | 2.633 s | 4 |
| 6 | 1,023.46 | 177.76 | 0.454 s | 2.880 s | 6 |

Reports:

- [c2 cold](../evidence/baseline-v3-short-c2-cold-20261014T141533.459043Z.json)
- [c4 cold](../evidence/baseline-v3-short-c4-cold-20261014T141556.551051Z.json)
- [c6 cold](../evidence/baseline-v3-short-c6-cold-20261014T141620.545218Z.json)

These runs recorded zero per-request retractions and zero sampled waiting/retracted
requests. `/v1/loads` supplied the active-count observations without enabling
Prometheus. The request-log audit found no unrelated generation starts inside
these three run windows. Nevertheless, other clients were active elsewhere in
the broader test session, so treat these as **preliminary screening**, not a
dedicated-window production qualification. The sample counts are too small for
reliable tail latency. Six short requests do not validate six full 256K contexts.

### Interface and retrieval checks

- [OpenAI smoke](../evidence/baseline-smoke-20261014T141158.742953Z.json): chat,
  separated reasoning, and synthetic tool calling passed.
- [1,024-token retrieval](../evidence/baseline-v2-retrieval-1k-c1-20261014T141444.080597Z.json):
  all three codes recalled, exact input count, 40 output tokens, about 0.321 s total.
- [32,768-token retrieval](../evidence/baseline-v3-retrieval-32k-c1-20261014T141650.627171Z.json):
  all three codes recalled, exact input count, 40 output tokens, about 1.095 s total
  and 1.005 s client-visible TTFT. This was one synthetic request, not broad recall
  or coding-quality validation. Snapshot sampling missed its short active interval.

### Excluded probes and harness corrections

1. [Original short c1 probe](../evidence/baseline-short-c1-cold-20261014T141202.991297Z.json):
   the brief codes-only answer stopped changing visible text while forced token
   generation continued. The initial text-based TPOT calculation was invalid.
   The report is retained with an [exclusion note](../evidence/baseline-initial-probe-caveat-20261014T141346.512785Z.json).
   Timing now tracks token-count-progress events and accounts for speculative
   multi-token first bursts; decode prompts request sustained explanatory output.
2. [Revised c1 cold probe](../evidence/baseline-v2-short-c1-cold-20261014T141349.428335Z.json):
   it observed two active requests while only one benchmark client was running.
   Other clients issued generation requests in the same window. Excluded from a
   clean single-user baseline; see its [qualification note](../evidence/baseline-single-user-traffic-caveat-20261014T141834.166981Z.json).
3. [Initial warm c1 attempt](../evidence/baseline-v2-short-c1-warm-20261014T141418.542402Z.json):
   stopped during warmup because the explanatory response omitted the three codes.
   No timed warm rounds ran. This exposed an inappropriate retrieval requirement
   in decode warmup, not an established cache failure. Decode warmup now checks
   accounting/runtime behavior; recall remains a separate retrieval-mode check.
   No warmed throughput result is qualified yet.

Regression tests cover invisible output tokens, speculative bursts, decode versus
retrieval validation, and stopping when observed active counts exceed client count.
Every original report is retained, including failed and excluded probes.

### Traffic audit, stop decision, and next work

[Traffic audit](../evidence/baseline-traffic-audit-20261014T141734.849434Z.json)
records unrelated generation requests from two client addresses during the broader
test session, including overlap with the excluded c1 probe. Raw logs were not saved.
Further inference was paused upon discovering that the initially idle condition
had not been maintained. Production clients were not blocked or disconnected.

The [post-test inventory](../evidence/postbaseline-benchmarks-20261014T141735.458833Z.json)
still matched the original configuration. No cache flush, service restart, driver
change or tuning change occurred.

Before the user-planned reboot, a further read-only check at 14:33 UTC found the
server ready and idle with the same original baseline. The pre-reboot inventory is
[`prereboot-handoff-20261014T143350.721160Z.json`](../evidence/prereboot-handoff-20261014T143350.721160Z.json).
The user's container has Docker restart policy `no`; see the
[`inference-context handoff`](INFERENCE_CONTEXT.md) for post-boot recovery checks.

Next, reserve a quiet window to rerun clean single-user timing, collect matched
warm-prefix measurements, and extend throughput tests to 32K and longer prompts.
Do not apply candidates or claim full-context six-user capacity from these results.

Run `python3 -B tests/summarize.py` to list evidence; exclusion notes are shown in
its status column. Compare only matched mode, prompt/output lengths and cache state.

## 2026-10-14 — post-reboot baseline, paused on prefix verification

The operator rebooted the host. The host driver/NVML now works at **580.178.04**.
With approval, the preserved original container was started at **14:42:54 UTC**;
no recreation, candidate, image pull, cache flush, or launch-argument change was
performed. The user then explicitly confirmed production idle for baseline testing.

- [Post-reboot inventory](../evidence/post-reboot-20261014T144706.029876Z.json):
  same container/image/argv and effective configuration, including 48-request cap,
  262,144 context and 1,587,968 shared token capacity. Start time changed as expected.
- The validator initially rejected that start-time change. The failed report is
  retained; identity/start-time checks were separated and all **48 offline tests**
  passed. [Read-only validation](../evidence/setup-validation-20261014T144756.418708Z.json) passed.
- [Interface smoke](../evidence/post-reboot-baseline-smoke-20261014T145553.690274Z.json):
  chat, separated reasoning and synthetic tool call passed.
- [Cold c1 decode](../evidence/post-reboot-baseline-short-c1-cold-20261014T145559.079649Z.json):
  three rounds of 1,024 input / exactly 512 output tokens passed. Median aggregate
  **257.83 tok/s**, per-request **257.94 tok/s**, TTFT **0.213 s**, duration **1.985 s**.
  Peak sampled active count was 1; zero sampled waiting/retracted requests and zero
  per-request retractions. Three samples are screening only; p95 is unavailable.
- [Warm c1 attempt](../evidence/post-reboot-baseline-short-c1-warm-20261014T145623.103132Z.json):
  one unforced warmup and one timed request used the **same prompt hash**, but the
  timed request reported **0 cached tokens**, failing the required ≥90% prefix reuse.
  Remaining rounds and all higher-concurrency/longer-context tests were stopped.
  Its timing is **not a qualified warmed throughput result**.
- [Traffic audit](../evidence/post-reboot-baseline-traffic-audit-20261014T145705.780144Z.json):
  access-record counts/routes matched all eight submitted requests (three smoke,
  three cold, two warm). No additional generation access records were observed;
  sampled loads afterward were zero active/waiting. Attribution and sampling remain
  limited; raw logs were not saved.

**Reproducibility caveat:** cached `main` moved from `970c569a…` to `236dfdf2…`.
`config.json` changed at `quantization_config.modules_to_convert`; the tokenizer
configuration hash stayed the same. Metadata does not prove which weights the
old process loaded. Keep pre/post-reboot results separate, not a matched checkpoint
comparison. See the [revision caveat](../evidence/post-reboot-model-revision-caveat-20261014T145842.572966Z.json).

Read-only source inspection suggests the hybrid cache's prompt-minus-one match
limit and Mamba branch checkpoints may require more than one warmup. This is a
**hypothesis**, not a confirmed cache defect or a successful fix. The
[session note](../evidence/post-reboot-baseline-session-note-20261014T145814.170489Z.json)
records source references/hashes and the observed failure.

The original service remains ready and idle at the last check. Next: review a
bounded extra-warmup diagnostic without weakening the ≥90% hit criterion, add
offline coverage for any harness change, and obtain approval before retrying live
inference. Do not advance to candidates until the failure and revision caveat are
reviewed. `configs/baseline.json` remains untouched.

### 15:02 UTC — approved bounded warmup diagnostic passed

The user approved diagnosis and a bounded single-client retry. Added explicit
`--warmup-passes` (1–3; default still 1) to the harness, with recorded pass/prompt
indices, no adaptive retry, and the original ≥90% measured-prefix criterion.
All **54 offline tests passed** before inference, including warmup bounds, failure
stops, retrieval validation and exclusion of warmups from timed samples.

After read-only inventory/validation, zero active/waiting requests and no generation
access records in the prior two minutes, ran exactly one diagnostic invocation:

- [Warm c1, two passes](../evidence/post-reboot-baseline-short-c1-warm-passes2-20261014T150239.380836Z.json):
  fresh 1,024-token prompt, up to 512 output tokens in each of two unforced warmups,
  then three forced 512-output timed requests. All five requests used the same
  prompt hash. Warmups reported **0 / 0** cached tokens; measured requests each
  reported **960 / 1,024 cached tokens (93.75%)** and passed.
- Median aggregate **245.23 tok/s**, per-request **245.35 tok/s**, TTFT **0.209 s**,
  duration **2.087 s**. Three samples do not establish tail latency or reliability.
  This verifies prefix reuse, **not a speed improvement** over the cold c1 screen.
- Peak sampled active count 1; zero sampled queue/retraction counts and zero
  per-request retractions. No configuration drift. Same post-reboot model metadata,
  image, argv, container identity and start time; immutable baseline integrity passed.
- [Session note and traffic audit](../evidence/warmup-diagnostic-session-note-20261014T150333.906426Z.json):
  exactly five successful `/generate` access records matched the five requests, no
  other generation routes observed, and zero active/waiting requests afterward.
  No raw logs were saved; access counts/sampling cannot exclude all interference.

The 0/0/960 pattern supports the hybrid cache branch-checkpoint explanation from
source inspection; internal state transitions were not traced. Two warmups were
sufficient **for this prompt**, not proof all workloads need exactly two. Earlier
one-pass failures remain failed and are not silently reclassified. The pre/post
reboot model-revision caveat remains in force.

The bounded diagnostic is complete. No c2/c4/c6, longer contexts, candidate changes,
restart or cache flush followed. Next baseline work is matched short cold/warm
concurrency screening, then 32K checks, in a confirmed idle window.

### 15:06–15:10 UTC — short c2/c4/c6 cold and warm screening passed

The user requested the next stage in the approved idle window. Read-only preflight
verified baseline effective settings, unchanged post-reboot container/start time
and cached model metadata, healthy host GPU queries, zero active/waiting requests,
and no generation access records in the preceding two minutes. All 54 offline
tests passed during validation. No harness or server configuration changes were made.

Each invocation used 1,024 input tokens, exactly 512 forced output tokens and three
timed rounds. Warm runs used two explicit sequential warmup passes per prompt.
Invocations were run individually, with a read-only traffic/load checkpoint before
advancing to the next case; no unattended matrix or 32K tests were run.

| Client concurrency | Cache | Median aggregate tok/s | Median per-request end-to-end tok/s | Median TTFT | Sampled peak active |
|---|---|---:|---:|---:|---:|
| 2 | Cold | 429.66 | 217.14 | 0.405 s | 2 |
| 2 | Warm | 430.33 | 219.96 | 0.401 s | 2 |
| 4 | Cold | 795.14 | 202.78 | 0.425 s | 4 |
| 4 | Warm | 779.94 | 201.20 | 0.409 s | 4 |
| 6 | Cold | 1,038.19 | 181.61 | 0.428 s | 6 |
| 6 | Warm | 1,063.95 | 182.33 | 0.416 s | 6 |

Reports: [c2 cold](../evidence/post-reboot-short-screen-c2-cold-20261014T150649.166657Z.json),
[c2 warm](../evidence/post-reboot-short-screen-c2-warm-passes2-20261014T150719.473189Z.json),
[c4 cold](../evidence/post-reboot-short-screen-c4-cold-20261014T150749.052146Z.json),
[c4 warm](../evidence/post-reboot-short-screen-c4-warm-passes2-20261014T150820.829474Z.json),
[c6 cold](../evidence/post-reboot-short-screen-c6-cold-20261014T150900.868018Z.json),
[c6 warm](../evidence/post-reboot-short-screen-c6-warm-passes2-20261014T150933.639441Z.json).

- All six runs passed. Every timed cold request reported **0 cached tokens**;
  every timed warm request reported **960/1,024 (93.75%)**.
- Zero per-request retractions and zero sampled waiting/retracted requests in every
  case. Active peaks 2/4/6 came from `/v1/loads`, not client-count inference.
- The [final traffic checkpoint](../evidence/short-screen-after-c6-warm-20261014T151013.920352Z.json)
  matched exactly **96 successful `/generate` records**: 72 timed requests and 24
  warmups. No additional generation access records were observed. Raw logs were not
  saved; access counts/sampling still cannot exclude all interference.
- The [session summary](../evidence/short-concurrency-session-summary-20261014T151051.774683Z.json)
  links inventories and records no effective-setting, container identity/start-time,
  or cached-model-metadata drift. Immutable baseline integrity passed; last loads
  showed zero active/waiting requests. Admission cap remains **48**, not 6.

These are short-input screening results, not production tail-latency qualification:
each case has only 6/12/18 timed samples, so no p95 is reported and cases are not
pooled. Small warm/cold differences do not establish a reliable speedup. Six short
requests do **not** validate six full-length contexts. The pre/post-reboot checkpoint
revision caveat continues to apply. Next: separately approved 32K single-client
retrieval first, then matched cold/warm decode checks.

### 15:14–15:15 UTC — 32K single-client retrieval and decode passed

With user approval, ran three individually reviewed baseline invocations at
concurrency 1 and **32,768 input tokens**, with a 512-output cap and three rounds
per case. Read-only preflight confirmed unchanged post-reboot identity/configuration
and model metadata, healthy GPU queries, zero active/waiting requests, and no
generation access records in the preceding two minutes. Offline validation passed
all 54 tests. The fresh per-request budget was 33,280 token slots, **2.096%** of the
observed 1,587,968 shared capacity, below the 90% guard.

- [Cold retrieval](../evidence/post-reboot-context32k-screen-retrieval-c1-cold-20261014T151404.925581Z.json):
  all three codes recalled in all three requests, with exact input accounting and
  **40 actual output tokens** per request (normal termination). Median TTFT
  **0.988 s**, request duration **1.079 s**. This is a scoped synthetic recall check,
  not broad retrieval or coding-quality qualification.
- Decode used explanatory prompts and exactly **512 forced output tokens**:

| Cache | Median aggregate output tok/s | Median TTFT | Median request duration | Cached tokens per timed request |
|---|---:|---:|---:|---:|
| Cold | 185.40 | 0.987 s | 2.761 s | 0 |
| Warm, two explicit warmups | 251.40 | 0.219 s | 2.036 s | 32,704 / 32,768 (99.80%) |

Reports: [cold decode](../evidence/post-reboot-context32k-screen-decode-c1-cold-20261014T151435.394325Z.json),
[warm decode](../evidence/post-reboot-context32k-screen-decode-c1-warm-passes2-20261014T151512.232734Z.json).
Warmup cache hits were 0 and 24,576; every timed warm request then verified 32,704
cached tokens. Warmups remain excluded from timing. Lower warm TTFT/end-to-end
latency reflects less prefill work, not proof of faster decode kernels (estimated
TPOT medians were about 3.48 ms cold and 3.55 ms warm).

All three cases passed with zero per-request retractions, zero sampled queue or
retraction counts, and sampled active peaks of 1. The
[traffic checkpoint](../evidence/context32k-after-decode-warm-20261014T151532.240551Z.json)
matched exactly **11 successful `/generate` records** (nine timed + two warmups),
with no additional generation access records observed; raw logs were not saved.
The [session summary](../evidence/context32k-session-summary-20261014T151603.715595Z.json)
links inventories and records unchanged effective settings, container identity/start,
model metadata and immutable baseline integrity. Last loads were zero active/waiting.

Only three timed requests per case: no p95/reliability qualification. Traffic
counts/sampling cannot exclude all interference; pre/post-reboot checkpoint
metadata differences still prohibit a matched comparison across reboot. No warm
retrieval, 32K multi-client, 100K/200K or near-limit test was included in this stage.
No candidate, restart, cache flush or server-configuration change occurred.

Next: approved 32K warm retrieval and bounded c2/c4/c6 cold/warm decode screening,
with fresh budgets and traffic checkpoints before advancing to larger contexts.

### 15:27 UTC — warm 32K retrieval passed; c2 cold stopped on queueing

The user approved the next stage: 32K warm retrieval, then individually reviewed
c2/c4/c6 cold/warm decode. Read-only preflight/validation passed, with all 54 offline
tests, unchanged post-reboot configuration/identity/model metadata, healthy host
GPU queries and zero active/waiting requests. Fresh token-budget checks passed at
c1/c2/c4/c6; passing a token budget is not a no-queue guarantee.

- [Warm c1 retrieval](../evidence/post-reboot-context32k-multi-retrieval-c1-warm-passes2-20261014T152706.864025Z.json)
  passed after two explicit warmups. All three timed requests recalled all three
  codes, used exactly 32,768 input / 40 actual output tokens, and reused
  **32,704/32,768 tokens (99.80%)**. Median TTFT **0.218 s**, duration **0.308 s**;
  zero observed queueing/retractions. Three synthetic requests are not broad quality
  or tail-latency qualification.
- [Cold c2 decode](../evidence/post-reboot-context32k-multi-decode-c2-cold-20261014T152724.696390Z.json)
  **failed the strict no-queue screening criterion in its first round**. Both
  submitted requests completed normally with exact 32,768 input / 512 output tokens,
  no cache hits and zero per-request retractions. Sampled peak active was 2,
  peak waiting **1**, peak retracted 0. Four queued client samples correspond to
  **three distinct published server timestamps**, not four queue events.
- Remaining rounds and all c2 warm/c4/c6 tests were stopped. Partial c2 timing is
  retained but **not a qualified no-queue concurrency result**. No larger-context,
  candidate, restart, cache flush, or configuration change followed.

The [stop checkpoint](../evidence/context32k-multi-after-c2-queue-stop-20261014T152746.732828Z.json)
matched all **seven successful `/generate` access records** (two retrieval warmups,
three timed retrieval requests, two failed-screen decode requests), with no extra
generation records observed. Its overall status remains failed because the c2
benchmark failed, not because access counts mismatched. No raw logs were saved.
The [session stop note](../evidence/context32k-multi-session-stop-note-20261014T152903.364433Z.json)
records unchanged configuration, container identity/start, cached model metadata
and immutable baseline integrity. Last service check was ready with zero active
and waiting requests. The admission cap remains **48**.

Read-only source inspection supports **transient chunked-prefill waiting** as an
explanation: the baseline uses an 8,192-token prefill chunk and a 16,384-token
prefill cap; new prefills compete for a per-batch chunk budget. `/v1/loads` reports
the running-batch and waiting-queue counts separately, so a zero running count
during prefill is not proof of GPU inactivity. This is source-consistent, not an
internally traced cause or evidence of pool exhaustion/server failure. Source
references/hashes are preserved in the stop note; queue-event duration is unknown.

**Further inference is paused.** Next: review an explicitly separate scheduling-aware
diagnostic to distinguish transient prefill waiting from sustained admission
queueing. Do not weaken the existing no-queue criterion, reclassify the failure,
retry, or apply a candidate without approval. Sampling/traffic-attribution limits
and the pre/post-reboot checkpoint caveat remain in force.

### 15:38 UTC — separate bounded prefill-queue diagnostic completed

The user approved a separate scheduling diagnostic, **not** a relaxation of the
normal benchmark policy. Added [`tests/prefill_diagnostic.py`](../tests/prefill_diagnostic.py)
and an additive optional first-text observer in the streaming client. The fixed
scope and diagnostic guards are specified in [`PREFILL_DIAGNOSTIC.md`](PREFILL_DIAGNOSTIC.md).
All **67 offline tests passed** before inference, including unchanged strict queue
rejection, fixed two-request flow, live confirmation guards, missing/stale/reset
telemetry, late repeated snapshots, first-text timing and failed-report preservation.

Read-only preflight verified unchanged baseline configuration, post-reboot identity
and model metadata, healthy GPU queries, idle loads, no generation access records
in the preceding two minutes, and a fresh 66,560-slot budget (4.192% of the shared
pool). Ran exactly **one cold c2 round**, two 32,768-token inputs / 512 forced outputs,
no warmups or retries. Both completed with exact counts, zero cache reuse and zero
per-request retractions.

The [diagnostic report](../evidence/prefill-queue-observation-c2-20261014T153800.779026Z.json)
records:

- Waiting peak **1**, running-batch peak **2**, retracted peak **0**.
- Seven queued client reads, representing **three unique published snapshots**.
  Their observed GET window was about **0.523–1.147 s after first submission**;
  this is not an exact queue-duration measurement.
- First visible text at **1.217 s and 1.952 s** after first submission. All queued
  reads finished before both requests had produced text. The first subsequent
  clear-queue read finished at **1.251 s**.
- Both cumulative prefill counters progressed during waiting. Full-round counter
  deltas are instrumentation observations, not exact per-request token accounting.
- No telemetry/safety errors, a newer idle publication after completion, and
  unchanged healthy effective configuration.

Classification: **consistent with transient chunked-prefill waiting**. This is
sampled temporal association, not an internal scheduler trace or proof of the
precise bottleneck. The diagnostic's `passed: true` applies only to its bounded
observation protocol; **`performance_qualified` is false**, and queueing was observed.
The original strict no-queue c2 failure remains failed. No c4/c6 or larger-context
test followed.

The [traffic audit](../evidence/prefill-queue-traffic-audit-20261014T153839.185505Z.json)
matched exactly two successful `/generate` access records, with no extra generation
records observed. The [session note](../evidence/prefill-queue-diagnostic-session-note-20261014T153919.090529Z.json)
links inventories, preserves the failed benchmark reference, and confirms unchanged
container identity/start, model metadata and immutable baseline integrity. Last
loads were zero active/waiting. No raw logs, server change, restart, flush or
candidate deployment occurred.

Next: review and approve a **separate scheduling-aware 32K throughput protocol**
that reports/bounds initial prefill waiting, rather than silently weakening strict
no-queue screening. The diagnostic alone does not authorize further live tests.
Traffic-attribution/sampling limits and the checkpoint-revision caveat still apply.

### 15:45–15:50 UTC — scheduling-aware 32K screening; stopped on unrelated traffic

The user requested the next scheduling-aware throughput stage. Added the explicitly
separate [`scheduled-32k-v1` protocol](SCHEDULED_SCREENING.md) and
[`tests/scheduled_benchmark.py`](../tests/scheduled_benchmark.py), sharing the
monitored-round engine with the diagnostic. The diagnostic CLI still fixes its
original c2/cold/one-round/five-second policy; the ordinary strict benchmark remains
zero-queue. All **76 offline tests passed** before live execution.

Each invocation selected one c2/c4/c6 workload and one cache state, using 32,768
input / exactly 512 forced output tokens and three timed rounds. Warm used two
explicit sequential warmup passes. The new protocol reports and bounds initial
prefill-associated waiting within eight seconds; it requires waiting reads to end
before all first-text arrivals and prefill-counter progress during waiting. Fresh
idle state is required between phases. This is **not strict no-queue qualification**.

Read-only preflight found unchanged baseline/post-reboot identity/model metadata,
healthy GPU queries, idle loads and no recent generation access records. Fresh
token budgets passed for c2/c4/c6 (4.192% / 8.383% / 12.575% of the shared pool).
Each invocation was reviewed with a traffic/load checkpoint before advancing.

| Client concurrency | Cache | Status | Median aggregate output tok/s | Median TTFT | Peak sampled waiting |
|---|---|---|---:|---:|---:|
| 2 | Cold | Screening passed | 260.57 | 1.584 s | 1 |
| 2 | Warm | Screening passed | 424.75 | 0.417 s | 0 |
| 4 | Cold | Screening passed | 332.94 | 2.672 s | 3 |
| 4 | Warm | Screening passed | 762.72 | 0.432 s | 0 |
| 6 | Cold | Screening passed | 367.11 | 3.655 s | 5 |
| 6 | Warm | Retry passed; initial attempt excluded | 1,023.31 | 0.442 s | 0 |

Reports: [c2 cold](../evidence/scheduled32k-screen-c2-cold-20261014T154547.930407Z.json),
[c2 warm](../evidence/scheduled32k-screen-c2-warm-20261014T154625.120550Z.json),
[c4 cold](../evidence/scheduled32k-screen-c4-cold-20261014T154657.666756Z.json),
[c4 warm](../evidence/scheduled32k-screen-c4-warm-20261014T154745.364905Z.json),
[c6 cold](../evidence/scheduled32k-screen-c6-cold-20261014T154827.684401Z.json),
[initial failed c6 warm](../evidence/scheduled32k-screen-c6-warm-20261014T154917.755044Z.json),
[c6 warm retry](../evidence/scheduled32k-screen-c6-warm-retry-20261014T172610.523920Z.json).

All completed cold rounds classified waiting as consistent with transient prefill
waiting. Their sampled running-batch peaks reached 2/4/6, not inferred client
counts. Passed warm c2/c4 rounds reported zero waiting and **32,704/32,768 cached
tokens per request (99.80%)**. No benchmark-request retractions were observed.

**Stop:** c6 warm completed its first timed round, then its second could not
establish a newer idle snapshot. Samples showed **7 running requests for 6 benchmark
clients**, with one still running after those six streams completed. The access
audit found an unrelated `/v1/chat/completions` request at **15:49:58 UTC**, overlapping
that phase. The third round was never submitted. The whole c6 warm invocation is
[excluded from comparison](../evidence/scheduled32k-c6-warm-traffic-caveat-20261014T155125.010684Z.json);
do not promote its partial summary or first round to a qualified warm c6 result.

The [final traffic checkpoint](../evidence/scheduled32k-after-c6-warm-stop-20261014T155016.447068Z.json)
recorded **90 benchmark `/generate` requests** (66 timed + 24 warmups) and one
unrelated chat request, so the isolated-window check failed. Checkpoints before
c6 warm had matched expected counts and reported idle. The
[session stop note](../evidence/scheduled32k-session-stop-note-20261014T155125.009749Z.json)
links inventories and confirms unchanged effective configuration, container
identity/start, cached model metadata and immutable baseline integrity. Last
sampled loads were zero active/waiting. Production clients were not blocked or
cancelled; no raw logs, restart, flush, candidate or server change occurred.

The next c6 warm retry was requested after the operator said the host should be
quiet as far as they could verify. A fresh preflight passed setup validation and
confirmed unchanged configuration, container identity/start, cached model metadata,
and healthy host GPU query. However, the traffic checkpoint for 15:50:16–16:14 UTC
found **three `/v1/chat/completions` accesses** and therefore failed isolation;
the point-in-time load sample was idle (zero running/waiting). **No retry inference
requests were submitted.** Preserve the failed checkpoint:
[preflight inventory](../evidence/scheduled32k-c6-warm-retry-preflight-20261014T161359.245264Z.json),
[setup validation](../evidence/setup-validation-20261014T161358.456617Z.json),
[traffic checkpoint](../evidence/scheduled32k-c6-warm-retry-preflight-traffic-20261014T161405.453823Z.json).

That 16:13 preflight remains a preserved failed checkpoint; no inference was sent
then. Following the operator's later best-effort quiet-window confirmation, fresh
preflight and traffic checks at 17:25 UTC passed, so the bounded c6 warm retry ran
once; see below. The earlier partial c6 warm invocation remains excluded.

### 17:25–17:27 UTC — c6 warm scheduling-aware retry completed

After the operator reconfirmed the best-effort quiet window, read-only setup and
inventory checks passed. Effective configuration, container identity/start, cached
model metadata, GPU query, and baseline evidence integrity matched; the six-request
budget was 199,680/1,587,968 token slots (12.575%). The traffic checkpoint since
17:23:59 UTC found no inference POSTs and zero running/waiting requests. Reports:
[pretest inventory](../evidence/scheduled32k-c6-warm-retry-pretest-20261014T172540.113048Z.json),
[setup validation](../evidence/setup-validation-20261014T172539.323933Z.json),
[preflight traffic](../evidence/scheduled32k-c6-warm-retry-preflight-traffic-20261014T172546.467529Z.json),
[preflight comparison](../evidence/scheduled32k-c6-warm-retry-preflight-comparison-20261014T172606.636914Z.json).

The one invocation used two sequential unforced warmup passes per prompt, then
three timed rounds: **12 warmups + 18 measured requests**, each 32,768 input / 512
output tokens. Every timed request reported 32,704 cached tokens (99.80%). All
rounds passed with `queue_not_reproduced`, peak waiting 0, and zero retractions;
aggregate output throughput was **1,023.31 / 1,045.42 / 975.13 tok/s**, median
**1,023.31 tok/s**. Median TTFT was **0.442 s** and median latency **2.891 s**;
p95 is unavailable at this sample count. Configuration remained unchanged.

The [post-run traffic checkpoint](../evidence/scheduled32k-c6-warm-retry-post-traffic-20261014T172702.541443Z.json)
matched exactly **30 `/generate` requests**, with no other inference routes found
and zero running/waiting requests afterward. This is a completed scheduling-aware
screening result, **not** a strict no-queue or production qualification
(`no_queue_qualified=false`, `production_qualified=false`). The initial c6 warm
partial run remains excluded; the strict c2 no-queue failure and pre/post-reboot
comparison caveat remain. No candidate or server configuration was changed; no
further inference is authorized by this result alone.

### 17:54 UTC — approved 100K c1 preflight blocked; no inference sent

The operator approved one run of the proposed
[`100K c1 cold retrieval protocol`](LONG_CONTEXT_100K.md) and confirmed the window
idle. Read-only setup validation passed; current configuration, container
identity/start, model metadata and GPU query matched the latest post-reboot
inventory. The c1 budget was **101,024/1,587,968 token slots (6.36%)**. However,
the traffic audit since the prior checkpoint found **43 `/v1/chat/completions`
requests**, all status 200, from **172.16.34.24** (17:27:47–17:31:05 UTC; latest
17:31:05). The address differs from the `.32.24` mentioned by the operator; this
audit recorded `.34.24`. The final load sample at 17:54 was idle, but the
traffic-isolation gate failed. **No `/generate` requests were submitted.**

Preserve the [pretest inventory](../evidence/baseline-100k-c1-pretest-20261014T175408.486909Z.json),
[setup validation](../evidence/setup-validation-20261014T175407.695485Z.json),
[failed traffic checkpoint](../evidence/baseline-100k-c1-preflight-traffic-20261014T175411.889925Z.json),
and [preflight comparison](../evidence/baseline-100k-c1-preflight-comparison-20261014T175502.157591Z.json).
The attempt is blocked, not a benchmark failure. Do not automatically retry; first
coordinate a fresh quiet window, then obtain explicit approval for another attempt.

### 18:26–18:27 UTC — 100K c1 cold retrieval passed

After a fresh operator confirmation, preflight passed: current post-reboot config,
container identity/start and cached-model metadata matched the previous inventory;
GPU query, setup validation and baseline-evidence integrity passed. No inference
accesses were recorded since 17:54:11 UTC, and loads were idle. The request budget
was **101,024/1,587,968 token slots (6.36%)**. See [pretest inventory](../evidence/baseline-100k-c1-pretest-retry-20261014T182618.370093Z.json),
[setup validation](../evidence/setup-validation-20261014T182617.519126Z.json),
[preflight traffic](../evidence/baseline-100k-c1-retry-preflight-traffic-20261014T182623.599096Z.json),
and [preflight comparison](../evidence/baseline-100k-c1-retry-preflight-comparison-20261014T182634.028041Z.json).

The strict `benchmark.py` retrieval path ran **three serial requests** at c1, each
with exactly 100,000 prompt tokens. All three retrieved every expected code, used
zero cached tokens, generated 40 tokens, and had zero retractions. Scheduler
telemetry sampled 132 times; peak running was 1 and peak waiting/retracted were 0.
Median TTFT was **3.377 s**, median end-to-end latency **3.468 s**, and the reported
short-answer completion rate was **11.53 tok/s** (not decode-throughput
qualification). p95 is unavailable at three requests. Configuration drift was
empty. Full [benchmark report](../evidence/baseline-100k-c1-cold-retrieval-20261014T182637.536737Z.json).

The [post-run traffic audit](../evidence/baseline-100k-c1-cold-retrieval-post-traffic-20261014T182709.573724Z.json)
matched exactly three `/generate` requests, found no other inference route, and
recorded zero active/waiting loads afterward. This passes only the proposed
synthetic 100K c1 retrieval screen. It does not authorize 200K, higher concurrency,
decode throughput, or candidate testing; the strict c2 32K failure remains intact.

### 20:46–20:47 UTC — 200K c1 cold retrieval passed

After separate explicit approval and a fresh quiet-window confirmation, preflight
passed setup validation, GPU health, baseline/configuration integrity, container
identity/start, cached-model metadata and the recent traffic check. The c1 budget
was **201,024/1,587,968 token slots (12.66%)**. See [pretest inventory](../evidence/baseline-200k-c1-pretest-20261014T204552.557870Z.json),
[setup validation](../evidence/setup-validation-20261014T204551.705969Z.json),
[preflight traffic](../evidence/baseline-200k-c1-preflight-traffic-20261014T204609.011337Z.json),
and [preflight comparison](../evidence/baseline-200k-c1-preflight-comparison-20261014T204618.502710Z.json).

The strict retrieval benchmark completed **three serial c1 requests**, each with
exactly 200,000 prompt tokens. All three recovered every expected code, reported
zero cached tokens, generated 40 tokens, and had zero retractions. Scheduler
telemetry sampled 204 times; peak running was 1 and peak waiting/retracted were 0.
Median TTFT was **7.754 s**, median end-to-end latency **7.845 s**. The reported
**5.10 output tok/s** is for the short 40-token retrieval answers, not decode
throughput qualification; p95 is unavailable at three requests. Configuration
drift was empty. Full [benchmark report](../evidence/baseline-200k-c1-cold-retrieval-20261014T204621.754710Z.json).

The [post-run traffic audit](../evidence/baseline-200k-c1-cold-retrieval-post-traffic-20261014T204705.576313Z.json)
matched exactly three `/generate` requests, found no other inference route, and
recorded zero active/waiting loads. This is a synthetic c1 retrieval screen only;
it does not authorize 260K, higher concurrency, decode throughput, or candidate
testing. The strict 32K c2 no-queue failure remains unchanged.

### 12:46–12:50 UTC — approved 260K c1 cold retrieval screen passed

The operator approved one exact near-limit attempt after the eight-hour quiet-window
check. The check found no Docker log entries during 04:20:17–12:20:17 UTC, and a
read-only load sample immediately afterward was idle. The operator confirmed the
server is dedicated to inference with no internal GPU activity. A fresh preflight
then verified the unchanged baseline configuration, container identity/start and
cached-model metadata; healthy host/container GPU queries; baseline evidence
integrity; and zero running/waiting requests. The budget was **261,024 / 1,587,968
slots (16.44%)**, within both context/input limits and the 90% pool guard. See the
[protocol](LONG_CONTEXT_260K.md), [preflight](../evidence/baseline-260k-c1-preflight-final-20261015T124651.694944Z.json),
and [pretest inventory](../evidence/baseline-260k-c1-pretest-20261015T124243.402471Z.json).

The strict benchmark ran exactly three serial c1 cold retrieval requests at 260,000
input tokens, with a 1,024-token output cap. All three recovered all codes, used
40 output tokens, reported zero cache hits and zero retractions. Sampled peak
running was 1; peak waiting/retracted were 0. Median TTFT was **11.242 s** and
median latency **11.335 s**. The **3.53 tok/s** figure is for 40-token retrieval
answers, not decode throughput; p95 is unavailable with three samples. The full
[benchmark report](../evidence/baseline-260k-c1-cold-retrieval-20261015T124657.082330Z.json)
passed.

The final [post-run audit](../evidence/baseline-260k-c1-post-traffic-final-20261015T125047.503452Z.json)
matched exactly three successful `/generate` records, with no other inference
routes; current loads were idle, and configuration/identity/model metadata were
unchanged. The log window also contained 101 timestamped non-access stderr lines
during the benchmark/post-inventory interval. No error/warning/exception markers
were detected, and the nearest access records were the expected `/v1/loads` and
`/get_server_info` reads; raw log text was not retained. Preliminary conservative
traffic reports remain preserved and are superseded for the decision by the final
reconciled checks. This qualifies only the specified synthetic 260K c1 retrieval
screen—not a full 262K prompt, decode throughput, production behavior, higher load,
or a retry. The strict 32K c2 no-queue failure remains unchanged.

### 14:31–14:34 UTC — approved 100K c1 cold/warm decode screen passed

After fresh setup validation and inventory, baseline/configuration/container/model
metadata matched the prior checkpoint; host/container GPU queries were healthy, the
fresh load sample was idle, and the c1 budget was **100,512 / 1,587,968 slots
(6.33%)**. The cold run completed three serial requests at exactly 100,000 input /
512 forced output tokens. Median aggregate rate was **99.44 tok/s**, median TTFT
**3.368 s**, and median end-to-end latency **5.148 s**. Every request reported zero
cached tokens and retractions. Sampled peak running was 1; waiting/retracted peaks
were 0. See the [cold report](../evidence/baseline-100k-c1-cold-decode-20261015T143114.453343Z.json)
and [cold post-traffic audit](../evidence/baseline-100k-c1-cold-decode-post-traffic-final-20261015T143305.625744Z.json).

After a separate between-run traffic/idle check passed, the warm run used two
explicit sequential unforced warmups and three timed requests. Median aggregate
rate was **243.75 tok/s**, median TTFT **0.242 s**, and median end-to-end latency
**2.100 s**. Timed requests reused **99,968/100,000 tokens (99.968%)** each; warmup
hits were 0 then 99,968. All timed requests generated exactly 512 tokens, with zero
retractions and zero sampled waiting. Sampled peak running was 1. The estimated
median TPOT was **3.50 ms cold / 3.64 ms warm**: the aggregate/TTFT improvement
primarily reflects cached prefill, not evidence of faster decode kernels. p95 is
unavailable at three timed samples. See the [between-run check](../evidence/baseline-100k-c1-warm-between-run-check-20261015T143328.877219Z.json),
[warm report](../evidence/baseline-100k-c1-warm-decode-passes2-20261015T143336.993764Z.json),
and [warm post-traffic audit](../evidence/baseline-100k-c1-warm-decode-post-traffic-20261015T143429.403552Z.json).

Both final audits matched the expected three cold / five warm successful `/generate`
accesses, found no other inference routes, and confirmed idle loads and unchanged
configuration/identity/model metadata. They recorded 57 cold and 46 warm timestamped
non-access stderr lines, with no error/warning/exception markers; raw logs were not
retained. An initial conservative cold audit is preserved and superseded for the
decision by the reconciled final audit. These are small c1 decode screens, not
production or tail-latency qualification. **200K decode and higher concurrency were
not run**; they require a separate protocol and explicit approval.

### 14:41–14:43 UTC — approved 200K c1 cold/warm decode screen passed

The operator separately approved the same staged decode protocol at 200K. Fresh
setup validation/inventory, baseline configuration and container/model-metadata
comparison, GPU queries, traffic, and idle checks passed. The budget was **200,512 /
1,587,968 slots (12.63%)**. Cold completed three serial requests at exactly 200,000
input / 512 forced output tokens: median aggregate rate **53.32 tok/s**, TTFT
**7.734 s**, and end-to-end latency **9.602 s**. All requests reported zero cache
hits and retractions; sampled peak running was 1, waiting/retracted 0. The [cold
report](../evidence/baseline-200k-c1-cold-decode-20261015T144110.873352Z.json) and
[post-traffic audit](../evidence/baseline-200k-c1-cold-decode-post-traffic-20261015T144223.017488Z.json)
passed.

After a separate passing between-run traffic/idle check, warm used two explicit
unforced warmups followed by three timed requests. Median aggregate rate was
**236.52 tok/s**, TTFT **0.288 s**, and end-to-end latency **2.164 s**. Warmup cached
counts were 0 then 196,608; each timed request reused **199,936/200,000 tokens
(99.968%)**. All timed outputs were exactly 512 tokens; there were zero retractions
and sampled waiting. Sampled peak running was 1. The estimated median TPOT was
**3.73 ms cold / 3.65 ms warm**. The aggregate-rate and TTFT change primarily
reflects avoided prefill, not a standalone decode-kernel speedup. p95 is unavailable
with three samples. See the [between-run check](../evidence/baseline-200k-c1-warm-between-run-check-20261015T144236.468801Z.json),
[warm report](../evidence/baseline-200k-c1-warm-decode-passes2-20261015T144239.473022Z.json),
and [warm post-traffic audit](../evidence/baseline-200k-c1-warm-decode-post-traffic-20261015T144331.196176Z.json).

Both final audits matched exactly three cold / five warm successful `/generate`
requests, found no other inference routes, and confirmed idle loads and unchanged
configuration/identity/model metadata. They recorded 93 cold and 57 warm timestamped
non-access stderr lines; no error/warning/exception markers were detected and raw
text was not retained. These are small c1 screens, not production or tail-latency
qualification. **260K decode and higher concurrency were not run** and need separate
protocols and explicit approval.

### 16:44 UTC — 0.88 c6 100K cold screen failed; stopped after one round

After a passing corrected preflight, one c6 round submitted six independent cold
100,000-input / 512-output decode prompts. All six completed exactly 512 tokens
with zero retractions, but sampled waiting peaked at **5**. The strict no-queue
benchmark failed and submitted no second or third rounds. The one-round aggregate
rate was **129.48 tok/s**, median TTFT **11.874 s**, and median latency **23.461 s**;
p95 is unavailable. Do not interpret this as a strict pass or advance to longer
contexts.

GPU memory also crossed the configured 3,072 MiB per-device sampled-free floor:
minimum free memory was **2,297 / 2,731 / 2,731 / 2,939 MiB**. No OOM or retraction
was reported; one-second sampling can miss peaks. Fresh post-run loads were idle,
candidate identity/config/model metadata were unchanged, and exact traffic matched
six successful `/generate` requests. The candidate remains running and the original
container preserved/stopped. **No retry or further c6 test was run.** See
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md) for the evidence files,
including the retained failed preflight reference comparison and corrected pass.

### 16:26–16:32 UTC — memory-088 running; startup, smoke and initial c1 screen passed

The operator explicitly authorized switching to 0.88 and beginning the initial
test. Baseline was idle, its image/argv matched, and recent traffic contained only
successful GETs. The original container was cleanly stopped and preserved. A new
`sglang-qwen38-flash-next-088` container reused the pinned image/runtime settings
and in-memory environment, changing only the launch memory fraction. No raw inspect,
environment or logs were retained, and no image was pulled or committed.

Actual shared token capacity is **1,717,184**, up **129,216 (+8.1%)**; active cap
remains 48, hybrid state slots increased from 611 to 656. Target KV allocation is
20.881 GiB. The 90% pool budget is about 1.545M; this is arithmetic, not six-user
qualification. Measured capacity exceeded the earlier illustrative estimate.

Smoke passed chat/reasoning/tool cases. Cold c1 decode passed three exact
32,768-input / 512-output requests: median aggregate 179.75 tok/s, TTFT 0.996 s,
latency 2.847 s, zero sampled waiting/retractions. First round was slower at 105.65
tok/s; this is not a controlled candidate speed comparison. Lowest sampled free
memory by GPU: 3,967 / 4,401 / 4,401 / 4,609 MiB, above the initial c1 review floor
of 2,048 MiB. Sampling does not establish transient peaks or OOM safety.

Both audits matched exact inference counts (three chat, then three generate),
found idle loads, and confirmed unchanged candidate identity/configuration/model
metadata. Candidate is **left running for testing**; original baseline is stopped
and preserved. Six-user long-context and 0.90 tests were not run. See
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md) for evidence links.

### 17:27–17:29 UTC — capacity-first rewrite and c6 cold 100K repeat PASSED

The operator explicitly requested replacing over-strict benchmark acceptance and
repeating the workload. New [policy](BENCHMARK_POLICY.md) makes ordinary queueing,
retractions, latency and low NVML-free memory observations/warnings, not automatic
capacity failures. It preserves correctness, request errors/timeouts, observed OOM,
health/config/container identity and traffic-isolation checks. No-queue and hard
free-memory floors are opt-in. Historical reports retain their original verdicts;
fixed scheduling diagnostic tools remain legacy reproducers, not new-test gates.

Fresh inventory/preflight passed for the unchanged memory-088 candidate with idle
loads and no recent inference. Starting GPU-free readings were 2,297 / 2,731 /
2,731 / 2,939 MiB. **Three rounds completed 18/18 cold requests**, each exactly
100,000 input and 512 output tokens, zero cached tokens and zero retractions.
No OOM or log error marker, restart, drift or unrelated inference was observed.

- Aggregate output rate per round: **137.04 / 135.19 / 137.42 tok/s**.
- Median aggregate **137.04 tok/s**, median TTFT **11.650 s**, median latency
  **22.290 s**. p95 unavailable (18 requests).
- Sampled running peak **6**, waiting peak **5**; queueing is included in timings.
- Minimum sampled free MiB per GPU: **2,285 / 2,719 / 2,719 / 2,927**, only 12 MiB
  below the starting readings. Low-memory warning retained; no mandatory floor.
- Service idle after each round and final audit; exact final access counts matched
  18 successful generation POSTs and all known GETs. The initial final-audit report
  had a one-GET expected-count arithmetic error, retained and corrected offline;
  no repeat inference was sent for that correction.

Result: **capacity-first-v1 PASS** for this bounded c6 100K workload, not production
or universal OOM qualification. The candidate remains running and the original
baseline stopped/preserved. No longer contexts or configuration changes were run.
Evidence and audit links are in [MEMORY_FRACTION_FIRST.md](MEMORY_FRACTION_FIRST.md).

### 17:34–17:38 UTC — capacity-first c6 cold 200K screen PASSED

After a fresh passing identity/idle/traffic preflight, the operator separately
approved six cold 200,000-input / 512-output requests in each of three rounds on
the unchanged memory-088 candidate. All **18/18 completed**, with zero cache hits,
zero request retractions, no observed OOM, no error markers, no restart/config/model
drift, and exact generation traffic. Sampled running reached **6** and sampled
waiting peaked at **5** (459/680 load snapshots); waiting is an observation, not a
capacity failure in the revised policy. The server was idle after each round and in
the final audit.

Results: per-round aggregate output **62.72 / 62.69 / 62.73 tok/s**, median
**62.72 tok/s**, median TTFT **27.234 s**, median latency **48.871 s**. The 90%
token-pool guard allowed the workload at **1,203,072 / 1,717,184 slots (70.1%)**.
Minimum sampled free memory was **2,265 / 2,697 / 2,699 / 2,905 MiB** and persisted
after idle; it remains a low-memory warning, not a hard failure. p95 is unavailable
with 18 requests; this is not production or universal OOM-safety qualification.

Evidence: pretest inventory, preflight, benchmark, posttest inventory and final
traffic/runtime audit are linked in [`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md).
The candidate remains running and the original baseline remains stopped/preserved.
No 230K/250K, 0.90, DP2 or HiCache experiment was run or implicitly authorized.

### 17:49–17:53 UTC — capacity-first c6 cold 250K screen PASSED

After a fresh passing idle/identity/traffic preflight, the operator approved six
cold 250,000-input / 512-output requests for each of three rounds on unchanged
memory-088. **18/18 completed**, with exact token accounting, zero cache hits and
zero retractions. No observed OOM, request/log error, restart, configuration drift
or unrelated inference. Sampled running reached **6**, waiting peaked at **5**
(638/907 load samples). Idle after each round and final audit; exact traffic matched.

Median aggregate output rate was **46.03 tok/s** (rounds 45.96 / 46.03 / 46.04),
median TTFT **37.612 s**, and median latency **66.641 s**. Reservation was
**1,503,072 / 1,717,184 slots (87.53%)**, leaving 42,393 tokens inside the 90%
guard. Minimum sampled free memory was **1,629 / 2,063 / 2,063 / 2,271 MiB**, a
634 MiB drop per GPU from pretest, retained after idle. This is an advisory low-memory
warning; no OOM was observed. The 18 requests do not provide p95 or universal OOM
safety evidence.

Preflight, benchmark, posttest inventory and final audit are linked from
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). The candidate remains running;
the original baseline remains stopped/preserved. At that stage, 256K, 0.90, DP2
and HiCache were not run or implicitly authorized.

### 18:04–18:09 UTC — capacity-first c6 250K / 4,096-output screen PASSED

The operator approved a one-factor extension: preserve six cold 250,000-input
prompts and the 0.88 configuration, increase forced output from 512 to 4,096 tokens,
three rounds. Fresh idle/identity/traffic preflight passed. The reservation was
**1,524,576 / 1,717,184 slots (88.78%)**, within the 90% guard by **20,889 slots**;
254,096 tokens per request fits the 262,144 context.

All **18/18 completed** with exact input/output counts, zero cache hits/retractions,
and no observed OOM, request/log errors, restart, configuration drift or unrelated
inference. Sampled running reached **6**, waiting peaked at **5** (639/1,154 load
samples); the service returned idle after every round and final audit.

Median aggregate output was **281.58 tok/s** (rounds 281.58 / 283.34 / 280.90),
median TTFT **37.647 s**, and median latency **86.579 s**. Minimum sampled free
memory remained **1,629 / 2,063 / 2,063 / 2,271 MiB**, unchanged from the 250K/512
screen; the low-memory warning persists. Eighteen samples do not provide p95 or
universal OOM-safety/production qualification.

Preflight, benchmark, posttest inventory and final audit are linked from
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Candidate remains running;
baseline remains stopped/preserved. At that stage, 256K, 0.90, DP2 and HiCache were
not run or implicitly authorized.

### 17:41–17:45 UTC — capacity-first c6 cold 230K screen PASSED

After a fresh passing identity/idle/traffic preflight, the operator approved six
cold 230,000-input / 512-output requests in each of three rounds on unchanged
memory-088. **18/18 completed**, with exact token counts, zero cache hits and zero
retractions. No observed OOM, request/log error, restart, drift or unrelated inference.
Sampled running reached **6**, waiting peaked at **5** (566/811 load samples); waiting
is diagnostic in this policy. The engine was idle after each round and final audit.

Median aggregate output was **51.77 tok/s** (rounds 51.70 / 51.90 / 51.77), median
TTFT **33.340 s**, and median latency **59.162 s**. The workload reserved
**1,383,072 / 1,717,184 slots (80.5%)**. Minimum sampled free memory was
**2,263 / 2,695 / 2,695 / 2,903 MiB**, close to pretest readings but below the
advisory 3 GiB warning. p95 is unavailable with 18 requests; this is not production
or universal OOM-safety qualification.

Pretest inventory, preflight, benchmark, posttest inventory and final audit are
linked in [`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). The candidate
remains running and the original baseline remains stopped/preserved. 250K, 0.90,
DP2 and HiCache were not run or implicitly authorized.

### 18:17–18:21 UTC — capacity-first c6 cold 256K/512 screen PASSED

The operator approved a near-guard stage: six cold 256,000-input / 512-output
requests, three rounds, with the same 0.88 configuration. Preflight verified the
ready/idle candidate, exact identity/config/model/GPU health, clean traffic window,
and intact baseline. The workload reserved **1,539,072 / 1,717,184 slots (89.63%)**,
leaving only **6,393 slots** under the 90% guard; prompt plus output fits the model
context.

All **18/18 completed** with exact token counts, zero cache hits/retractions, and no
observed OOM, request/log errors, restart, configuration drift or unrelated traffic.
Sampled running reached **6**, waiting peaked at **5** (662/932 load samples), and
the service returned idle after each round and final audit.

Median aggregate output was **44.57 tok/s** (rounds 44.44 / 44.59 / 44.57), median
TTFT **38.786 s**, and median latency **68.856 s**. Minimum sampled free memory
remained **1,629 / 2,063 / 2,063 / 2,271 MiB**; low-memory warning persists. Eighteen
samples do not provide p95 or universal OOM-safety/production qualification.

Preflight, benchmark, posttest inventory and final audit are linked from
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Candidate remains running;
baseline remains stopped/preserved. No larger-output, 0.90, DP2 or HiCache test was
run or implicitly authorized.

### 18:31–18:39 UTC — five-round c6 cold 250K/4096 repeat PASSED

The operator approved extending the same six-user, cold 250K-input / 4,096-output
workload from three to five rounds. Fresh preflight passed; configuration and
container were unchanged, service idle, and the 90% token-pool guard passed at
**1,524,576 / 1,717,184 slots (88.78%)**.

All **30/30 requests completed** with exact token accounting, zero cache hits and
zero retractions. No observed OOM, request/log error, restart, drift or unrelated
inference. Sampled running reached **6**, waiting peaked at **5** (1,064/1,915 load
samples). Idle after each round and final audit; exact traffic matched 30 generation
POSTs. Minimum sampled free memory stayed **1,629 / 2,063 / 2,063 / 2,271 MiB**.

Median aggregate output was **282.50 tok/s**; median latency **86.547 s**, initial
p95 **86.956 s**; median TTFT **37.630 s**, initial p95 **63.782 s**. Thirty samples
give only a weak p95 view, not a production-tail guarantee. The low-memory warning
persists; no universal OOM-safety claim follows.

Evidence: preflight, benchmark, posttest inventory and final audit are linked in
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Candidate remains running;
original baseline remains stopped/preserved. No further stage was authorized.

### 19:18–19:34 UTC — ten-round c6 cold 250K/4096 repeat PASSED

The operator approved ten rounds of the same six-user cold 250,000-input /
4,096-output workload. Fresh preflight passed: unchanged 0.88 candidate, idle
service, clean traffic window, intact baseline, and guarded budget **1,524,576 /
1,717,184 slots (88.78%)**, with **20,889 slots** of headroom.

All **60/60 requests completed** with exact input/output accounting, zero cache hits
and zero retractions. No observed OOM, request/log error, restart, drift, or unrelated
inference. Sampled running reached **6**, waiting peaked at **5** (2,129/3,884 load
samples). Final audit matched exact traffic (60 generation requests), confirmed idle
loads and unchanged identity/configuration. Minimum sampled free memory remained
**1,629 / 2,063 / 2,063 / 2,271 MiB**.

Median aggregate output was **282.60 tok/s**; median latency **86.438 s**, initial
p95 **88.551 s**; median TTFT **37.656 s**, initial p95 **63.769 s**. The n=60 p95
is a limited estimate, not production-tail qualification. Queueing and low-memory
warnings persist; no universal OOM-safety claim follows.

Pretest, preflight, benchmark, posttest inventory and final audit are linked in
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Candidate remains running
and idle; baseline remains stopped/preserved. No further stage was authorized.

### 19:43–20:00 UTC — staggered c6 cold 250K/4096 comparison PASSED

The operator approved ten c6 rounds with six cold 250,000-input / 4,096-output
requests per round, starting one second apart. Fresh preflight passed with the same
ready/idle 0.88 candidate and a clean traffic window. Budget was unchanged at
**1,524,576 / 1,717,184 slots (88.78%)**, leaving **20,889 slots** of guarded
headroom.

All **60/60 requests completed** with exact counts, zero cache hits/retractions, and
no observed OOM, request/log error, restart, drift, or unrelated inference. Client
starts matched planned offsets 0–5 seconds within **0.4 ms**. Sampled running reached
**6**, waiting peaked at **5** (2,093/3,839 load samples). Final audit matched exact
traffic and confirmed idle loads with unchanged identity/configuration. Per-GPU free
memory minima remained **1,629 / 2,063 / 2,063 / 2,271 MiB**.

Median aggregate output was **283.45 tok/s**; median latency **83.829 s**, initial
p95 **86.211 s**; median TTFT **35.019 s**, initial p95 **58.604 s**. Compared with
the separate synchronized n=60 screen, these sample percentiles were lower, but the
independent runs do not establish a stable or causal improvement. p95 remains a
limited estimate; the low-memory warning persists.

Evidence: pretest, preflight, benchmark, posttest inventory and final audit are
linked in [`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Candidate remains
running and idle; original baseline remains stopped/preserved. No further stage was
authorized.

## 21:44–21:53 UTC — matched MTP-off startup blocked; no inference

The approved matched comparison remained **64K input / 2K output cap, c6, three
cold rounds**, with prompt hashes fixed to `coding-mtp-ab-v1`. A fresh MTP-on
preflight passed and a stopped candidate was created from the pinned image and
runtime. Docker normalized `HostConfig.OomKillDisable` from unset to explicit
`false`; all other host/runtime settings and the environment matched, and no
environment values were recorded.

The MTP-off candidate became ready with memory fraction **0.88**, attention backend
**FlashInfer**, and speculation disabled. Effective shared-token capacity was
**1,536,000** (MTP-on: **1,717,184**). The top-level `max_running_requests` field was
null, but the server's internal state explicitly reported
`effective_max_running_requests_per_dp: 245`; this is an admission-limit metric, not
observed active concurrency. The first startup gate rejected the workload because
the harness did not yet consume that explicit metric. It also found one unaccounted
`POST /v1/chat/completions` and one `[other-route]` GET. The harness sent **zero
inference requests**. The startup audit recorded zero OOM markers and 10 generic
error-marker lines; raw logs were not retained.

After that discovery, the MTP-off candidate was stopped only after two idle load
samples five seconds apart. The preserved 0.88 MTP-on candidate was restored and
verified ready/idle; its restoration audit also observed unaccounted chat/API routes.
The matched MTP-off benchmark was **not run**, so there is no MTP-off performance or
coding-quality result. A new quiet-window confirmation and fresh traffic-isolation
preflight are required before resuming.

The offline harness now accepts a reported per-DP effective request cap for DP1 when
the top-level cap is missing, requires duplicate values to agree, and never sums TP
copies. Validation passed **106 tests**.

Evidence: [MTP-on inventory](../evidence/coding-mtp-ab-on-pretest-20261015T214009.827196Z.json),
[retained initial preflight parser failure](../evidence/coding-mtp-ab-on-preflight-20261015T214131.740110Z.json),
[corrected passing preflight](../evidence/coding-mtp-ab-on-preflight-20261015T214158.186490Z.json),
[runtime recheck](../evidence/coding-mtp-ab-off-runtime-recheck-20261015T214420.126039Z.json),
[startup attempt](../evidence/coding-mtp-ab-off-startup-preflight-20261015T214916.572298Z.json),
[effective off configuration and traffic audit](../evidence/coding-mtp-ab-off-capacity-blocked-20261015T214955.740080Z.json),
[source verification of the per-DP admission metric](../evidence/coding-mtp-ab-effective-cap-source-20261015T215707.289169Z.json),
[restore gate](../evidence/coding-mtp-ab-off-restore-gate-20261015T215021.695660Z.json), and
[restoration verification](../evidence/coding-mtp-ab-on-restored-after-off-20261015T215307.776144Z.json).

## 22:00–22:06 UTC — confirmed-window retry blocked by traffic; no inference

After the operator reconfirmed isolation, the fresh MTP-on preflight passed with
exact expected read-only access counts, idle loads, unchanged identity/configuration,
and the fixed coding prompt hashes. The preserved MTP-off candidate was restarted
serially. With the harness fix, its startup passed profile, 0.88 memory fraction,
FlashInfer backend, speculation-disabled, effective DP1 admission-cap (**245**),
context and pool-budget checks. Effective capacity remained **1,536,000** slots.

The startup traffic audit nevertheless recorded one unaccounted
`POST /v1/chat/completions` and one `[other-route]` GET. These were not sent by the
harness; no MTP-off inference was sent. The candidate was stopped after a fresh
five-second idle/quiet gate. The same 0.88 MTP-on container was restored and verified
ready/idle at 22:06 UTC. Its restoration audit also recorded those unaccounted route
classes. The A/B remains incomplete; the newly confirmed window did not establish
actual isolation. Obtain and verify client isolation before another attempt.

Evidence: [fresh MTP-on inventory](../evidence/coding-mtp-ab-on-pretest-retry-20261015T215952.152359Z.json),
[passing on-arm preflight](../evidence/coding-mtp-ab-on-preflight-retry-20261015T220014.335304Z.json),
[off startup preflight](../evidence/coding-mtp-ab-off-startup-preflight-retry-20261015T220258.001541Z.json),
[idle restore gate](../evidence/coding-mtp-ab-off-restore-gate-retry-20261015T220336.506789Z.json), and
[MTP-on restoration](../evidence/coding-mtp-ab-on-restored-after-off-20261015T220629.921439Z.json).

## 00:41–00:47 UTC, 2026-10-16 — third MTP-off startup blocked; no inference

A fresh MTP-on inventory and preflight passed with exact expected read-only traffic,
idle loads, unchanged identity/configuration, and matching coding prompts. The
preserved MTP-off candidate was restarted serially. Its effective configuration,
per-DP request cap (**245**), 64K/2K context, and shared-pool budget all passed the
updated harness checks. Effective capacity remained **1,536,000** slots.

The startup audit again recorded one unaccounted `POST /v1/chat/completions` and one
`[other-route]` GET. The harness sent **zero inference requests**. The off candidate
was stopped after two idle load samples and a quiet five-second interval; MTP-on was
restored and verified ready/idle at 00:47 UTC. The restoration audit also observed
unaccounted routes. The A/B remains incomplete; identify and pause the source before
another profile switch.

Evidence: [fresh on-arm inventory](../evidence/coding-mtp-ab-on-pretest-finaltry-20261016T004102.926691Z.json),
[passing on-arm preflight](../evidence/coding-mtp-ab-on-preflight-finaltry-20261016T004121.518558Z.json),
[off startup preflight and traffic audit](../evidence/coding-mtp-ab-off-startup-preflight-finaltry-20261016T004409.479664Z.json),
[restore gate](../evidence/coding-mtp-ab-restore-gate-finaltry-20261016T004427.285691Z.json), and
[MTP-on restoration](../evidence/coding-mtp-ab-on-restored-after-off-20261016T004713.382186Z.json).
