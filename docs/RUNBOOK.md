# Safe execution and restoration runbook

Current benchmark acceptance rules are in [BENCHMARK_POLICY.md](BENCHMARK_POLICY.md).
New runs use capacity-first screening; zero waiting and 3 GiB free memory are not
mandatory pass conditions. Existing evidence retains its historical criteria.

## Setup boundary

The setup records configuration and prepares code. It does not generate tokens,
flush caches, change admission, enable metrics, load drivers, restart containers,
or install services. Do not treat offline unit-test success as live qualification.

## Before baseline inference tests

1. Obtain approval for a quiet/idle test window. Coordinate with clients; the
   `--confirm-idle` flag is an operator assertion, not proof the engine is idle.
2. Check the container is still running and save an inventory:
   `python3 -B tests/capture_baseline.py --label pretest`.
3. Compare against `configs/baseline.json`. The test scripts reject unexpected
   changes in the captured profile. Always record any image, build, tokenizer,
   model, network, or workload changes, even if flags look identical.
4. Review GPU usage via `docker exec sglang-qwen38-flash-next nvidia-smi`.
   Do not assume the host GPU monitor works or that another model will fit.
5. Run interface smoke checks, then the smallest cold and warm benchmark cases.
   Move to longer contexts only after smaller retrieval checks pass.
6. Use three rounds for screening only. Collect at least 30 request samples
   for an initial p95 view; this still does not establish reliable production tails.

## Example progression — ONLY in the approved idle window

```bash
python3 -B tests/smoke_test.py --label baseline-smoke --execute --confirm-idle
python3 -B tests/benchmark.py --label baseline-short-c1 \
  --prompt-tokens 1024 --output-tokens 256 --concurrency 1 \
  --execute --confirm-idle
python3 -B tests/benchmark.py --label baseline-short-c6-warm \
  --prompt-tokens 1024 --output-tokens 1024 --concurrency 6 --cache warm \
  --execute --confirm-idle
python3 -B tests/benchmark.py --label baseline-retrieval-32k \
  --mode retrieval --prompt-tokens 32768 --output-tokens 1024 --concurrency 1 \
  --execute --confirm-idle
```

Warm decode tests first perform sequential unforced warmups on the explanatory
decode prompt, then forced-output timing runs. Retrieval checks use their own
codes-only prompt and must be run separately; their output limit must leave enough
room for all codes. Warm retrieval runs also validate recall during warmup.

The default is one warmup pass. For an explicitly approved hybrid-cache diagnostic,
`--cache warm --warmup-passes 2` (maximum 3) repeats each prompt in bounded sequential
passes before timing. All warmups remain outside the measured sample set. Require
≥90% cached tokens on every timed request; do not silently add passes after a failed
timed round. Preserve failures and stop before considering a separately approved retry.

The harness rejects prompt/output/context overflows, automatic truncation, client
concurrency beyond the effective admission cap, DP configurations other than DP1,
and total requested occupancy above 90% of the observed shared token pool. This
budget is not a guarantee against hybrid-state exhaustion or OOM.

## Stop conditions

- Any failed mode-specific correctness check, truncation, token-count mismatch,
  request failure/timeout, observed OOM, configuration drift, restart or health failure.
- Unrelated inference traffic or inability to audit a memory candidate's runtime.
- Queueing, retractions and low sampled free memory are reported warnings in capacity
  mode. They fail only under an explicitly selected stricter policy/hard floor.
- Do not proceed to the next workload after a failure. Retain its report.

The harness stops later rounds after request failures or validation failures; a
round already submitted can remain in flight. Client timeouts/interruption do
not prove server requests have been cancelled. Check the service before retrying.
Metrics are sampled rather than exhaustive; absent events do not prove none occurred.
No automatic stop/restart/cancel/flush operation is implemented.

The `/v1/loads` snapshot works on this build without enabling Prometheus. An initial
nonzero active/waiting count rejects a run. Sampled active counts above benchmark
client concurrency stop subsequent rounds, but traffic that fits below that count
can still interfere. Audit request timestamps and reserve a quiet window before
treating the measurements as clean candidate-comparison baselines.

## Separate scheduling diagnostic

For reproducing a separately approved, fixed 32K c2 scheduling observation, use the
[prefill diagnostic protocol](PREFILL_DIAGNOSTIC.md). It allows bounded initial
waiting under that legacy protocol, submits exactly two
requests once, and is not a performance qualification. Its completion does not
authorize further rounds or higher loads. Verify any pending requests after a
client timeout; no implicit cancellation/restart is performed.

For reproducing older fixed-32K scheduling-aware screening, see
[`SCHEDULED_SCREENING.md`](SCHEDULED_SCREENING.md). New general capacity tests use
`benchmark.py --policy capacity` without its fixed prefill-duration cap. Review one
invocation and its traffic audit before advancing. If other clients resume, pause
and reconfirm coordinated isolation; an instantaneous idle sample is insufficient.

## Before any candidate deployment — separate approval required

1. Resolve the host driver/NVML mismatch or establish a reviewed, working recovery
   procedure before stopping a healthy production process. No reboot is implied.
2. Preserve the existing container, exact image ID, model cache, and relevant
   credentials privately. Do not remove the container or pull over the image tag.
3. `profiles.py NAME` prints candidate argv and expected effective settings; it
   does not validate model/backend compatibility or CUDA graph allocation.
4. Use the pinned image ID from the baseline, not a mutable `:latest` or model tag.
   Preserve mounts, GPU requests, IPC, network/port mapping, entrypoint, and security
   settings. Do not copy the H200 host-network/systemd arrangement onto this node.
5. Verify the cached model/tokenizer revision. The snapshot's cached `main` ref is
   not proof of what an already-running server loaded. Pin revisions in a separately
   documented reproducibility profile rather than silently changing the baseline.
6. Arrange an explicit maintenance window and rollback before modifying anything.
   GPUs are nearly fully occupied; assume candidates must be tested serially.
7. After an approved deployment, wait for readiness, capture a new inventory, compare
   effective settings, rerun smoke checks, then repeat matched baseline workloads.

## Restoration

No service changes were made by setup, so there is nothing to roll back now.
For future approved experiments, retain the original container as the restoration
target instead of deleting/recreating it. Candidate deployment must include a
reviewed procedure for releasing the candidate's GPUs and host port and returning
the original container to service. Even starting the original stopped container
can fail while the host driver mismatch persists; it is not a guaranteed rollback.

After restoration, verify `/get_server_info` and `/v1/models`, capture a new
inventory, compare original argv/image/limits, and run separately approved smoke
checks. Do not claim restoration from a container status alone.
