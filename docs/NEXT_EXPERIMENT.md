# Next actions after the operator's reboot

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

**The approved baseline screens through 200K c1 are complete.** The 100K and 200K
c1 cold retrieval screens passed after their own preflight and approval. They are
functional synthetic retrieval checks, not production or decode-throughput
qualification. Preserve the strict c2 32K no-queue failure and the distinction
between scheduling-aware screening and strict qualification. See `results.md` and
the [`100K`](LONG_CONTEXT_100K.md) / [`200K`](LONG_CONTEXT_200K.md) protocols.
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
approved c6 warm retry. The 100K and 200K c1 cold retrieval screens also passed
under separate protocols. No further inference is pending; any 260K or higher-load
test requires its own protocol, approval and quiet-window check. See the linked
long-context protocols.
Use the traffic audit, `/v1/loads`, request timing and the selected protocol's
explicit queue criterion (zero for strict benchmarks; bounded initial prefill
waiting for scheduled screening). Stop on unrelated traffic, out-of-policy
queueing, failure, drift or retraction.

After the 200K c1 screen, a near-limit 260K single-session test may be considered
only with a separate protocol, budget review and approval. Multi-session tests
need separate confirmation, fresh budget calculations and successful lower-size
checks. Six full-length contexts are not qualified by the short c6 throughput run.

Any future live test needs its own reviewed protocol, explicit user/operator
approval, a fresh traffic check, and both confirmation switches. Such a test sends
inference; it is **not** an offline check. Keep the original 48-request
configuration as the baseline; do not deploy any experimental candidate without
separate approval.
