# Next actions after the operator's reboot

New runs use [capacity-first policy](BENCHMARK_POLICY.md). Queueing and the former
3 GiB floor are advisory; runtime/OOM, workload accounting and health checks remain.

**Latest completed benchmark (20:00 UTC): PASS.** The approved ten-round c6 cold 250K/4096 run
with one-second staggered starts completed 60/60 requests without observed OOM or
retractions. Median aggregate 283.45 tok/s; initial p95 TTFT 58.604 s and latency
86.211 s (limited n=60 estimate); minimum GPU-free was 1,629 MiB. Candidate was
unchanged at final audit. The operator approved a focused coding A/B: NEXTN/MTP on
versus off, 64K prompt / 2K output cap, c6, three rounds per profile. The on arm
passed 18/18. A matched FlashInfer-pinned MTP-off candidate started with speculation
disabled, but its startup audit found one unaccounted chat POST and one unknown GET;
no off-arm inference was sent. Effective capacity was 1,536,000 slots. The reported
top-level active cap was null, while SGLang exposed an explicit per-DP effective cap
of 245; the offline harness now uses that metric without summing duplicate TP
values. The off container was stopped after idle checks, and MTP-on was restored and
verified ready/idle at 21:53 UTC. Reconfirm an isolated window before any profile
switch or further inference. See `CODING_OPTIMIZATION_PLAN.md` and
`SESSION_HANDOFF.md`.

**Live status (2026-10-15, 16:32 UTC):** the operator authorized the 0.88 switch
and initial screen. `sglang-qwen38-flash-next-088` is running; the original is
preserved and stopped. Actual capacity is 1,717,184 slots. Smoke and initial
32K c1 decode passed; the service is idle. Next is reviewed six-user candidate
screening, not further baseline characterization or a 0.90 change. See
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md). Earlier planning/status
entries below are historical.

**Historical update (16:45 UTC):** 0.88 c6 100K cold failed strict no-queue after
one round (peak sampled waiting 5), and sampled free memory breached the 3 GiB floor
(minimum 2,297 MiB). All six requests completed with zero retractions; no later
round/retry was sent. Do not advance to 200K or larger tests. Candidate remains
ready and idle; original baseline remains preserved/stopped. See
[`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md).

**First decision gate:** quantify the capacity gain and runtime-memory risk of
0.88/0.90 before DP2 or HiCache. See [`MEMORY_FRACTION_FIRST.md`](MEMORY_FRACTION_FIRST.md).
Read-only estimates suggest 0.88 may already meet six 250K inputs plus 512 outputs
within the pool guard; capacity and OOM safety remain unvalidated. No live changes
are authorized by the planning request.

**Planning direction (2026-10-15):** prioritize six-user long-context capacity and
responsiveness, including feasibility branches for DP2 and HiCache. See
[`SIX_USER_CAPACITY_PLAN.md`](SIX_USER_CAPACITY_PLAN.md). This is a plan, not
authorization for further inference, harness changes, or service changes.

**Current status (2026-10-15, 14:43 UTC):** the separately approved **260K c1 cold
retrieval** and **100K/200K c1 cold/warm decode** screens passed. Warm timed requests
reused 99,968/100,000 tokens at 100K and 199,936/200,000 at 200K after two explicit
warmups; all runs had zero sampled waiting/retractions and the service was idle
afterward. These are scoped screens, not production/tail-latency or full-context
qualification. No further inference is pending. 260K decode, full 262K prompts,
higher concurrency, repeats, and candidates each need a separate protocol, fresh
checks, and explicit approval. See the [`260K`](LONG_CONTEXT_260K.md), [`100K decode`](LONG_CONTEXT_DECODE_100K.md),
[`200K decode`](LONG_CONTEXT_DECODE_200K.md), and [`results.md`](results.md).

**Current status (2026-10-14, 20:47 UTC):** reboot recovery is complete. Host driver
580.178.04 is healthy; the preserved original container was started with approval
and is ready. Post-reboot baseline smoke and short 1,024/512 cold/warm screening at
c1/c2/c4/c6 passed; warm runs used **two explicit warmups** and reused 960/1,024
tokens on every timed request. Initial one-pass failures are retained. No candidate
was applied; the admission cap remains 48. See [`results.md`](results.md) for reports
and the continuing model-revision caveat.

The approved **32K c1 cold retrieval and cold/warm decode stage also passed**:
all codes recalled in three retrieval requests; median decode throughput 185.40
cold / 251.40 warm output tok/s, TTFT 0.987 / 0.219 s. Warm measured requests reused
32,704/32,768 tokens with two explicit warmups.

The next approved stage passed **32K warm c1 retrieval**, but **cold c2 decode
failed the strict no-queue criterion in its first round** (peak waiting 1).
Both decode requests completed with zero retractions. At that stage the remaining
strict c2 rounds, c2 warm/c4/c6 and larger contexts were not run; the service
remained ready and idle. The later, distinct scheduling-aware results follow below.

A separately approved **one-round c2 scheduling diagnostic is now complete**.
Waiting peak 1 occurred in early observations (about 0.523–1.147 s after submission),
with prefill-counter progress; first text arrived at 1.217/1.952 s. Both requests
completed without retractions, followed by a fresh idle publication. This supports
transient prefill waiting, not an internally traced cause or performance
qualification. See [`PREFILL_DIAGNOSTIC.md`](PREFILL_DIAGNOSTIC.md) and `results.md`.

The separately approved [scheduling-aware 32K protocol](SCHEDULED_SCREENING.md)
has now completed c2/c4/c6 cold and warm screening. Median aggregate cold/warm rates
were 260.57/424.75 (c2), 332.94/762.72 (c4), and 367.11/1,023.31 (c6) output tok/s.
Cold prefill waiting was explicitly reported, not treated as a no-queue pass. The
first c6 warm attempt remains excluded after traffic overlap; its separately
authorized retry passed three rounds (18 timed requests), with zero sampled waiting
or retractions and exact post-run traffic accounting. See `results.md` and the linked
evidence.

**The approved long-context retrieval screens through 260K c1 are complete.** The
100K, 200K, and 260K c1 cold retrieval screens passed after their own preflight and
approval. Separate 100K and 200K c1 cold/warm decode screens also passed. These are
scoped synthetic screens, not production or tail-latency qualification. Preserve
the strict c2 32K no-queue failure and the distinction between scheduling-aware
screening and strict qualification. See `results.md` and the linked long-context
protocols.
Do not restart, flush, or change server settings. Any harness change needs offline
tests.
The recovery sequence below is retained for future use; it is not the current
execution queue.

## 1. Verify host GPU driver health

```bash
cat /proc/driver/nvidia/version
nvidia-smi
```

Before reboot, the kernel driver was 580.173.02 but host NVML was 580.178 and
`nvidia-smi` failed. Check for a healthy, matching driver now. If the mismatch
persists, stop and review host driver/library package state separately. Do not
reinstall/upgrade, reboot again, or make privileged system changes as part of an
inference benchmark.

## 2. Inspect and, if desired, start the existing container

```bash
docker ps -a --filter name=sglang-qwen38-flash-next
docker inspect --format '{{.Id}} {{.Image}} {{.State.Status}} {{.HostConfig.RestartPolicy.Name}}' sglang-qwen38-flash-next
```

The current container's restart policy is `no`, so Docker will not auto-start it
after host reboot. Once driver health is confirmed, if the user wants the existing
inference service back online:

```bash
docker start sglang-qwen38-flash-next
```

Start only that pre-existing container. Do not `docker run`, recreate it, pull the
mutable `lmsysorg/sglang:qwen38flashnext` tag, change policy, or apply candidates.
If startup fails, preserve the logs as appropriate privately; do not replace the
service before reviewing the cause. Startup/weight-load will likely take minutes.

## 3. Verify readiness and recapture context

```bash
python3 -B tests/validate_setup.py --inventory
python3 -B tests/capture_baseline.py --label post-reboot
```

Check `/get_server_info`, `/v1/models`, `/v1/loads`, existing container/image ID,
SGLang build, exact launch argv, 262144-token context, effective input limit,
48-request cap, 1,587,968 shared token capacity, and TP4/EP4/DP1 settings.
Record any differences as post-reboot evidence; do not rewrite the immutable
pre-reboot baseline. Compare startup capacity and GPU telemetry. A changed model
cache revision is not proof of which weights were loaded by the old process.

## 4. Further experiments require separate approval

Cold and two-pass warm 1,024/512 decode checks at c1/c2/c4/c6 are now recorded.
32K c1 cold/warm retrieval and cold/warm decode are also recorded. Strict no-queue
c2 cold screening failed on waiting count 1; a separate bounded diagnostic supports
early prefill waiting but is not a performance qualification. Scheduling-aware
screening now completed all c2/c4/c6 cold and warm cases after the separately
approved c6 warm retry. The 100K, 200K, and 260K c1 cold retrieval screens also
passed under separate protocols. No further inference is pending; any repeat,
full-context, higher-load, or candidate test requires its own protocol, approval and
quiet-window check. See the linked long-context protocols.
Use the traffic audit, `/v1/loads`, request timing and the selected protocol's
explicit queue criterion (zero for strict benchmarks; bounded initial prefill
waiting for scheduled screening). Stop on unrelated traffic, out-of-policy
queueing, failure, drift or retraction.

The 260K single-session screen is complete under its own protocol. A full 262K or
multi-session test still needs separate protocol review, explicit approval, fresh
budget calculations and successful lower-size checks. Six full-length contexts are
not qualified by the short c6 throughput run.

Any future live test needs its own reviewed protocol, explicit user/operator
approval, a fresh traffic check, and both confirmation switches. Such a test sends
inference; it is **not** an offline check. Keep the original 48-request
configuration as the baseline; do not deploy any experimental candidate without
separate approval.
